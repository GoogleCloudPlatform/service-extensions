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
import pytest
import grpc
import sys
import os
from concurrent import futures
from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.service.auth.v3 import attribute_context_pb2 as attr_pb2
from envoy.config.core.v3 import base_pb2
from envoy.type.v3 import http_status_pb2
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from example.block_ip.service_callout_example import CalloutServerExample

# Create a direct test server instance
def create_test_server():
    """Create a test server and client."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    server_instance = CalloutServerExample(
        cert_chain_path=None,
        private_key_path=None
    )
    auth_pb2_grpc.add_AuthorizationServicer_to_server(server_instance, server)
    port = server.add_insecure_port('[::]:0')  # Use any available port
    server.start()
    
    # Create a client channel
    channel = grpc.insecure_channel(f'localhost:{port}')
    stub = auth_pb2_grpc.AuthorizationStub(channel)
    
    return server, stub, channel

# Setup and teardown for all tests
server, client, channel = create_test_server()

def teardown_module(module):
    """Tear down resources after all tests."""
    channel.close()
    server.stop(0)

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

def test_ip_blocking_denied():
    """Test that requests from blocked IPs are denied."""
    request = create_request_with_xff('10.0.0.1, 192.168.1.1')
    response = client.Check(request)

    assert response.HasField('denied_response')
    assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
    assert response.denied_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.denied_response.headers[0].header.value == 'false'

def test_ip_allowed():
    """Test that requests from allowed IPs are permitted."""
    request = create_request_with_xff('192.168.1.1, 10.0.0.1')
    response = client.Check(request)

    assert response.HasField('ok_response')
    assert response.ok_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.ok_response.headers[0].header.value == 'true'

def test_missing_x_forwarded_for():
    """Test that requests without x-forwarded-for header are denied."""
    # Create a CheckRequest without x-forwarded-for header
    request = auth_pb2.CheckRequest(
        attributes=attr_pb2.AttributeContext(
            request=attr_pb2.AttributeContext.Request(
                http=attr_pb2.AttributeContext.HttpRequest(
                    headers={}
                )
            )
        )
    )

    response = client.Check(request)

    assert response.HasField('denied_response')
    assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
    assert response.denied_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.denied_response.headers[0].header.value == 'false'

def test_invalid_ip():
    """Test that requests with invalid IPs are denied."""
    request = create_request_with_xff('invalid-ip-address')
    response = client.Check(request)

    assert response.HasField('denied_response')
    assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
    assert response.denied_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.denied_response.headers[0].header.value == 'false'
