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

from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.service.auth.v3 import attribute_context_pb2 as attr_pb2
from envoy.type.v3 import http_status_pb2
import grpc
import pytest

from extauthz.example.block_ip.service_callout_example import (
    CalloutServerExample as CalloutServerTest,
)
from extauthz.service.callout_server import CalloutServerAuth, _addr_to_str


class ServerSetupException(Exception):
    pass


class NoResponseError(Exception):
    pass


# Replace the default ports of the server so that they do not clash with running programs.
default_kwargs: dict = {
    'address': ('localhost', 8443),
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


def create_request_with_xff(xff_value: str) -> auth_pb2.CheckRequest:
    """Helper to create a request with X-Forwarded-For header."""
    return auth_pb2.CheckRequest(
        attributes=attr_pb2.AttributeContext(
            request=attr_pb2.AttributeContext.Request(
                http=attr_pb2.AttributeContext.HttpRequest(
                    headers={'x-forwarded-for': xff_value}
                )
            )
        )
    )


class TestBlockIPServer(object):
    """Test server functionality for IP blocking."""

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_ip_blocking_denied(self, server: CalloutServerTest) -> None:
        """Test that requests from blocked IPs are denied."""
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            
            request = create_request_with_xff('10.0.0.1, 192.168.1.1')
            response = make_request(stub, request)

            assert response.HasField('denied_response')
            assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
            denied_headers = {header.header.key: header.header.value for header in response.denied_response.headers}
            assert denied_headers.get('x-client-ip-allowed') == 'false'

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_ip_allowed(self, server: CalloutServerTest) -> None:
        """Test that requests from allowed IPs are permitted."""
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            
            request = create_request_with_xff('192.168.1.1, 10.0.0.1')
            response = make_request(stub, request)

            assert response.HasField('ok_response')
            ok_headers = {header.header.key: header.header.value for header in response.ok_response.headers}
            assert ok_headers.get('x-client-ip-allowed') == 'true'

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_missing_x_forwarded_for(self, server: CalloutServerTest) -> None:
        """Test that requests without x-forwarded-for header are denied."""
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            
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
            assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
            denied_headers = {header.header.key: header.header.value for header in response.denied_response.headers}
            assert denied_headers.get('x-client-ip-allowed') == 'false'

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_invalid_ip(self, server: CalloutServerTest) -> None:
        """Test that requests with invalid IPs are denied."""
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            
            request = create_request_with_xff('invalid-ip-address')
            response = make_request(stub, request)

            assert response.HasField('denied_response')
            assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
            denied_headers = {header.header.key: header.header.value for header in response.denied_response.headers}
            assert denied_headers.get('x-client-ip-allowed') == 'false'

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_basic_server_health_check(self, server: CalloutServerTest) -> None:
        """Test that the health check sub server returns the expected 200 code."""
        assert server.health_check_address is not None
        response = urllib.request.urlopen(
            f'http://{_addr_to_str(server.health_check_address)}')
        assert not response.read()
        assert response.getcode() == 200


_secure_test_args: dict = {
    "kwargs": default_kwargs | {
        'secure_health_check': True
    },
    "test_class": CalloutServerTest
}


@pytest.mark.parametrize('server', [_secure_test_args], indirect=True)
def test_https_health_check(server: CalloutServerTest) -> None:
    """Test that the health check sub server returns the expected 200 code."""
    assert server.health_check_address is not None
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    response = urllib.request.urlopen(
        f'https://{_addr_to_str(server.health_check_address)}',
        context=ssl_context)
    assert not response.read()
    assert response.getcode() == 200


def test_custom_server_config() -> None:
    """Test that port customization connects correctly."""
    server: CalloutServerTest | None = None
    try:
        ip = 'localhost'
        port = 8446
        plaintext_port = 8083
        health_check_port = 8003

        server = test_server = CalloutServerTest(
            address=(ip, port),
            plaintext_address=(ip, plaintext_port),
            health_check_address=(ip, health_check_port))
        # Start the server in a background thread
        thread = threading.Thread(target=test_server.run)
        thread.daemon = True
        thread.start()
        wait_till_server(lambda: getattr(test_server, '_setup', False))

        response = urllib.request.urlopen(f'http://{ip}:{health_check_port}')
        assert response.read() == b''
        assert response.getcode() == 200

        with grpc.insecure_channel(f'{ip}:{plaintext_port}') as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            request = create_request_with_xff('192.168.1.1')
            response = make_request(stub, request)
            assert response.HasField('ok_response')

        # Stop the server
        test_server.shutdown()
        thread.join(timeout=5)
    except Exception as ex:
        raise ServerSetupException(
            'Failed to connect to the callout server.') from ex
    finally:
        if server:
            del server


_no_health_args: dict = {
    "kwargs": default_kwargs | {
        'combined_health_check': True
    },
    "test_class": CalloutServerTest
}


@pytest.mark.parametrize('server', [_no_health_args], indirect=True)
def test_custom_server_no_health_check(server: CalloutServerTest) -> None:
    """Test that the server only connects to the specified addresses.

    The server should not connect to the health check port if its disabled 
    in the setup config.
    """
    address = _local_test_args['kwargs']['health_check_address']
    # Connect to the default health check address to confirm the port is open.
    test_server = HTTPServer(address, BaseHTTPRequestHandler)
    del test_server
    assert getattr(server, '_health_check_server', None) is None
