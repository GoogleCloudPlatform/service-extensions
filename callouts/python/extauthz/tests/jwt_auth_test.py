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
import time
from concurrent import futures
from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.service.auth.v3 import attribute_context_pb2 as attr_pb2
from envoy.config.core.v3 import base_pb2
from envoy.type.v3 import http_status_pb2
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from example.jwt_auth.service_callout_example import JwtAuthServer

# Test data
VALID_JWT_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjE3MzQ2MSwiZXhwIjoyMDc1NjU4MjYxfQ.Vv-Lwn1z8BbVBGm-T1EKxv6T3XKCeRlvRrRmdu8USFdZUoSBK_aThzwzM2T8hlpReYsX9YFdJ3hMfq6OZTfHvfPLXvAt7iSKa03ZoPQzU8bRGzYy8xrb0ZQfrejGfHS5iHukzA8vtI2UAJ_9wFQiY5_VGHOBv9116efslbg-_gItJ2avJb0A0yr5uUwmE336rYEwgm4DzzfnTqPt8kcJwkONUsjEH__mePrva1qDT4qtfTPQpGa35TW8n9yZqse3h1w3xyxUfJd3BlDmoz6pQp2CvZkhdQpkWA1bnwpdqSDC7bHk4tYX6K5Q19na-2ff7gkmHZHJr0G9e_vAhQiE5w"
INVALID_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkphbmUgRG9lIn0.kD4LNVVCOJOiOH6_9x_CFH-R4MId-i_LiJ9My4G4Crs"

# Create a direct test server instance
def create_test_server():
    """Create a test server and client."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Initialize the server with a mocked public key path for testing
    server_instance = JwtAuthServer(
        cert_chain_path=None,
        private_key_path=None
    )
    
    # Mock the public key method for testing
    server_instance._load_public_key = lambda path: None
    # Use the public key from test_certs folder or mock it directly
    server_instance.public_key = os.path.join(os.path.dirname(__file__), 'test_certs/publickey.pem')
    
    auth_pb2_grpc.add_AuthorizationServicer_to_server(server_instance, server)
    port = server.add_insecure_port('[::]:0')
    server.start()
    
    # Create a client channel
    channel = grpc.insecure_channel(f'localhost:{port}')
    stub = auth_pb2_grpc.AuthorizationStub(channel)
    
    return server, stub, channel, server_instance

# Setup and teardown for all tests
server, client, channel, server_instance = create_test_server()

def teardown_module(module):
    """Tear down resources after all tests."""
    channel.close()
    server.stop(0)

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

def test_valid_jwt_token():
    """Test that requests with valid JWT tokens are allowed."""
    # Mock the validate_jwt_token method to return a valid decoded token
    original_validate_method = server_instance.validate_jwt_token
    server_instance.validate_jwt_token = lambda token: {
        'sub': '1234567890',
        'name': 'John Doe',
        'admin': True
    }
    
    auth_header = f"Bearer {VALID_JWT_TOKEN}"
    request = create_request_with_auth_header(auth_header)
    response = client.Check(request)
    
    # Restore the original method
    server_instance.validate_jwt_token = original_validate_method
    
    assert response.HasField('ok_response')
    # Verify decoded fields were added as headers
    assert any(h.header.key == 'decoded-sub' and h.header.value == '1234567890' 
               for h in response.ok_response.headers)
    assert any(h.header.key == 'decoded-name' and h.header.value == 'John Doe' 
               for h in response.ok_response.headers)
    assert any(h.header.key == 'decoded-admin' and h.header.value == 'True' 
               for h in response.ok_response.headers)

def test_invalid_jwt_token():
    """Test that requests with invalid JWT tokens are denied."""
    # Mock the validate_jwt_token method to return None (invalid token)
    original_validate_method = server_instance.validate_jwt_token
    server_instance.validate_jwt_token = lambda token: None
    
    auth_header = f"Bearer {INVALID_JWT_TOKEN}"
    request = create_request_with_auth_header(auth_header)
    response = client.Check(request)
    
    # Restore the original method
    server_instance.validate_jwt_token = original_validate_method
    
    assert response.HasField('denied_response')
    assert response.denied_response.status.code == http_status_pb2.StatusCode.Unauthorized
    assert response.denied_response.body == "Authorization token is invalid."

def test_missing_jwt_token():
    """Test that requests without JWT tokens are denied."""
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
    
    response = client.Check(request)
    
    assert response.HasField('denied_response')
    assert response.denied_response.status.code == http_status_pb2.StatusCode.Unauthorized
    assert response.denied_response.body == "No Authorization token found."
