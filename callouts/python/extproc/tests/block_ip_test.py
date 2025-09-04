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
from concurrent import futures
from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.service.auth.v3 import attribute_context_pb2 as attr_pb2
from envoy.type.v3 import http_status_pb2
from extproc.example.block_ip.service_callout_example import CalloutServerExample

@pytest.fixture(scope='module')
def auth_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_pb2_grpc.add_AuthorizationServicer_to_server(CalloutServerExample(), server)
    port = server.add_insecure_port('[::]:0')
    server.start()
    
    yield server, port
    
    server.stop(0)

@pytest.fixture
def auth_client(auth_server):
    server, port = auth_server
    channel = grpc.insecure_channel(f'localhost:{port}')
    stub = auth_pb2_grpc.AuthorizationStub(channel)
    
    yield stub
    
    channel.close()

def test_ip_blocking_denied(auth_client):
    """Test that requests from blocked IPs are denied."""
    # Create a CheckRequest with a blocked IP in x-forwarded-for header
    request = auth_pb2.CheckRequest(
        attributes=attr_pb2.AttributeContext(
            request=attr_pb2.AttributeContext.Request(
                http=attr_pb2.AttributeContext.HttpRequest(
                    headers={'x-forwarded-for': '10.0.0.1, 192.168.1.1'}
                )
            )
        )
    )

    response = auth_client.Check(request)

    assert response.HasField('denied_response')
    assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
    assert response.denied_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.denied_response.headers[0].header.value == 'false'

def test_ip_allowed(auth_client):
    """Test that requests from allowed IPs are permitted."""
    # Create a CheckRequest with an allowed IP
    request = auth_pb2.CheckRequest(
        attributes=attr_pb2.AttributeContext(
            request=attr_pb2.AttributeContext.Request(
                http=attr_pb2.AttributeContext.HttpRequest(
                    headers={'x-forwarded-for': '192.168.1.1, 10.0.0.1'}
                )
            )
        )
    )

    response = auth_client.Check(request)

    assert response.HasField('ok_response')
    assert response.ok_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.ok_response.headers[0].header.value == 'true'

def test_missing_x_forwarded_for(auth_client):
    """Test that requests without x-forwarded-for header are allowed."""
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

    response = auth_client.Check(request)

    assert response.HasField('ok_response')
    assert response.ok_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.ok_response.headers[0].header.value == 'true'

def test_invalid_ip(auth_client):
    """Test that requests with invalid IPs are allowed."""
    # Create a CheckRequest with an invalid IP
    request = auth_pb2.CheckRequest(
        attributes=attr_pb2.AttributeContext(
            request=attr_pb2.AttributeContext.Request(
                http=attr_pb2.AttributeContext.HttpRequest(
                    headers={'x-forwarded-for': 'invalid-ip-address'}
                )
            )
        )
    )

    response = auth_client.Check(request)

    assert response.HasField('ok_response')
    assert response.ok_response.headers[0].header.key == 'x-client-ip-allowed'
    assert response.ok_response.headers[0].header.value == 'true'
