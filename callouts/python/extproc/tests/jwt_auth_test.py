# Copyright 2024 Google LLC.
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
import re

import jwt
from envoy.config.core.v3.base_pb2 import HeaderMap
from envoy.config.core.v3.base_pb2 import HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc

import grpc
import pytest

from extproc.example.jwt_auth.service_callout_example import (
    CalloutServerExample as CalloutServerTest)
from extproc.service.callout_tools import add_header_mutation
from extproc.tests.basic_grpc_test import (
    make_request,
    setup_server,
    get_insecure_channel,
    insecure_kwargs,
)


# Import the setup server test fixture.
_ = setup_server
_local_test_args = {"kwargs": insecure_kwargs, "test_class": CalloutServerTest}

@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_jwt_auth_rs256_failure(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="Authorization", raw_value=b"")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    request_headers = service_pb2.HttpHeaders(headers=header_map,
                                              end_of_stream=True)

    # Use request_headers in the request
    with pytest.raises(grpc.RpcError) as e:
      make_request(stub, request_headers=request_headers)
    assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED

@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_jwt_auth_rs256_success(server: CalloutServerTest) -> None:
    with get_insecure_channel(server) as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)

        # Load the private key
        private_key_path = './extproc/ssl_creds/localhost.key'
        with open(private_key_path, 'r') as key_file:
            private_key = key_file.read()

        # Define the payload for the JWT
        payload = {
            "sub": "1234567890",
            "name": "John Doe",
            "admin": True,
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }

        # Generate the JWT token
        jwt_token = jwt.encode(payload, private_key, algorithm="RS256")

        # Authorization header value
        authorization_header_value = f"Bearer {jwt_token}"

        # Construct the HeaderMap
        header_map = HeaderMap()
        header_value = HeaderValue(key="Authorization", raw_value=bytes(authorization_header_value, 'utf-8'))
        header_map.headers.extend([header_value])

        # Construct HttpHeaders with the HeaderMap
        request_headers = service_pb2.HttpHeaders(headers=header_map, end_of_stream=True)

        # Construct the decoded items list from the payload
        decoded_items = [(f'decoded-{key}', str(value)) for key, value in payload.items() if key != 'exp' and key != 'iat']
        # Adding formatted 'iat' and 'exp' to match the test format
        decoded_items.extend([
            ('decoded-iat', str(int(payload['iat'].timestamp()))),
            ('decoded-exp', str(int(payload['exp'].timestamp())))
        ])

        value = make_request(stub, request_headers=request_headers)
        assert value.HasField('request_headers')
        # Instead of directly comparing the full response, check the presence and basic validation of decoded items
        assert 'header_mutation' in str(value)
        for key, expected_value in decoded_items:
          # Check presence of key
          assert key in str(value)
          # For 'iat' and 'exp', check if it matches the pattern since the value will be different
          if key in ['decoded-iat', 'decoded-exp']:
            pattern = rf'{key}"\s*raw_value:\s*"\d+"'
            assert re.search(pattern, str(value)), f"{key} does not match expected pattern"
          else:
            # For other keys, check the exact value
            pattern = rf'{key}"\s*raw_value:\s*"{expected_value}"'
            assert re.search(pattern, str(value)), f"{key} value {expected_value} not found"