# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import print_function

import datetime
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
import threading
import time
from typing import Iterator, Callable, Any, Mapping
import urllib.request
import ssl
from unittest.mock import patch

from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.service.auth.v3 import attribute_context_pb2 as attr_pb2
from envoy.type.v3 import http_status_pb2
import grpc
import pytest

from extauthz.example.jwt_auth.service_callout_example import (
    JwtAuthServer as CalloutServerTest,
)
from extauthz.service.callout_server import CalloutServerAuth, _addr_to_str


class ServerSetupException(Exception):
    pass


class NoResponseError(Exception):
    pass


default_kwargs: dict = {
    'address': ('localhost', 8443),
    'plaintext_address': ('localhost', 8080),
    'health_check_address': ('localhost', 8000)
}
# Arguments for running a custom CalloutServer with testing parameters.
_local_test_args: dict = {
    "kwargs": default_kwargs,
    "test_class": CalloutServerTest
}


def get_plaintext_channel(server: CalloutServerAuth) -> grpc.Channel:
    """From a CalloutServer, obtain the plaintext address and create a grpc channel pointing to it.

    Args:
        server: Server to connect to.
    Returns:
        grpc.Channel: Open channel to the server.
    """
    addr = server.plaintext_address
    return grpc.insecure_channel(_addr_to_str(addr) if addr else '')


def wait_till_server(server_check: Callable[[], bool], timeout: int = 10):
    """Wait until the `server_check` function returns true.

    Used for blocking until the server reaches a given state.
    Times out after a given time.

    Args:
        server_check: Function to check.
        timeout: Wait time. Defaults to 10.
    """
    expiration = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
    while not server_check() and datetime.datetime.now() < expiration:
        time.sleep(1)


def _start_server(server: CalloutServerAuth) -> threading.Thread:
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    # Wait for the server to start
    wait_till_server(lambda: getattr(server, '_setup', False))
    return thread


def _stop_server(server: CalloutServerAuth, thread: threading.Thread):
    # Stop the server
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope='class', name='server')
def setup_server(request) -> Iterator[CalloutServerAuth]:
    """Set up basic CalloutServer.

    Takes in two optional pytest parameters.
    'kwargs': Arguments passed into the server constructor. 
      Default is the value of default_kwargs.
    'test_class': Class to use when constructing the server.
      Default is the base CalloutServer.

    Yields:
        Iterator[CalloutServerAuth]: The server to test with.
    """
    params: dict = request.param or {'kwargs': {}, 'test_class': None}
    kwargs: Mapping[str, Any] = default_kwargs | params['kwargs']
    # Either use the provided class or create a server using the default CalloutServer class.
    server = (params['test_class'] or CalloutServerAuth)(**kwargs)
    try:
        thread = _start_server(server)
        yield server
        _stop_server(server, thread)
    finally:
        del server


def make_request(stub: auth_pb2_grpc.AuthorizationStub, request: auth_pb2.CheckRequest) -> auth_pb2.CheckResponse:
    """Make a request to the server.

    Args:
        stub: The server stub.
        request: The CheckRequest to send.

    Returns: The CheckResponse returned from the server.
    """
    try:
        return stub.Check(request)
    except Exception as e:
        raise NoResponseError(f"Request failed: {e}")


def create_request_with_auth_header(auth_header: str) -> auth_pb2.CheckRequest:
    """Helper to create a request with Authorization header."""
    return auth_pb2.CheckRequest(
        attributes=attr_pb2.AttributeContext(
            request=attr_pb2.AttributeContext.Request(
                http=attr_pb2.AttributeContext.HttpRequest(
                    headers={'authorization': auth_header}
                )
            )
        )
    )


class TestJwtAuthServer(object):
    """Test server functionality for JWT authentication."""

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_valid_jwt_token(self, server: CalloutServerTest) -> None:
        """Test that requests with valid JWT tokens are allowed."""
        # Mock the validate_jwt_token method to return a valid decoded token
        with patch.object(server, 'validate_jwt_token', return_value={
            'sub': '1234567890',
            'name': 'John Doe', 
            'admin': True,
            'iat': 1712173461,
            'exp': 2075658261
        }):
            with get_plaintext_channel(server) as channel:
                stub = auth_pb2_grpc.AuthorizationStub(channel)
                
                auth_header = "Bearer valid_token"
                request = create_request_with_auth_header(auth_header)
                response = make_request(stub, request)

                assert response.HasField('ok_response')
                # Verify decoded fields were added as headers
                ok_headers = {header.header.key: header.header.value for header in response.ok_response.headers}
                assert ok_headers.get('decoded-sub') == '1234567890'
                assert ok_headers.get('decoded-name') == 'John Doe'
                assert ok_headers.get('decoded-admin') == 'True'

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_invalid_jwt_token(self, server: CalloutServerTest) -> None:
        """Test that requests with invalid JWT tokens are denied."""
        # Mock the validate_jwt_token method to return None (invalid token)
        with patch.object(server, 'validate_jwt_token', return_value=None):
            with get_plaintext_channel(server) as channel:
                stub = auth_pb2_grpc.AuthorizationStub(channel)
                
                auth_header = "Bearer invalid_token"
                request = create_request_with_auth_header(auth_header)
                response = make_request(stub, request)

                assert response.HasField('denied_response')
                assert response.denied_response.status.code == http_status_pb2.StatusCode.Unauthorized
                assert "Authorization token is invalid" in response.denied_response.body

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_missing_jwt_token(self, server: CalloutServerTest) -> None:
        """Test that requests without JWT tokens are denied."""
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            
            # Create a request without the Authorization header
            request = auth_pb2.CheckRequest(
                attributes=attr_pb2.AttributeContext(
                    request=attr_pb2.AttributeContext.Request(
                        http=attr_pb2.AttributeContext.HttpRequest(
                            headers={}
                        )
                    )
                )
            )
            response = make_request(stub, request)

            assert response.HasField('denied_response')
            assert response.denied_response.status.code == http_status_pb2.StatusCode.Unauthorized
            assert "No Authorization token found" in response.denied_response.body

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_basic_server_health_check(self, server: CalloutServerTest) -> None:
        """Test that the health check sub server returns the expected 200 code."""
        assert server.health_check_address is not None
        response = urllib.request.urlopen(
            f'http://{_addr_to_str(server.health_check_address)}')
        assert not response.read()
        assert response.getcode() == 200
