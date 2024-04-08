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

from envoy.config.core.v3.base_pb2 import HeaderMap
from envoy.config.core.v3.base_pb2 import HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc
import grpc
import pytest

from extproc.example.validate_token.service_callout_example import (
    CalloutServerExample as CalloutServerTest)
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
def test_request_header_valid_token(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="authentication", raw_value=b"test")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    mock_headers = service_pb2.HttpHeaders(headers=header_map,
                                           end_of_stream=True)

    response = make_request(stub, request_headers=mock_headers)

    assert response.HasField('request_headers')

@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_header_validation_failure(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="authorization", raw_value=b"compromisedtoken789")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    request_headers = service_pb2.HttpHeaders(headers=header_map,
                                              end_of_stream=True)

    # Use request_headers in the request
    with pytest.raises(grpc.RpcError) as e:
      make_request(stub, request_headers=request_headers)
    assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED
