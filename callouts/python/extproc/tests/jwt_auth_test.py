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

    jwt_token = 'Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjc3Njc2MSwiZXhwIjoyMDc1NjU2NzYxfQ.BSH8s_MexJJYrFqKld-PwaUu3ovXu-ZfBcfsqiFtWQVHtcJu1Q0PHFLfBSx_9Uu57Uzfj2DoALVe-rF7VZoBfB-gFSbNVSneF7kLrpVD_E84ItZINzBqta5UyTdO0T4PHZtB9m_lmZq-u9IPUNF4h_GeWKRAEVwxzp46szBytFuAIEW0mlIoKxYUSlaHxCLqXz9tYyGJe9ZQpBp_tLRnvQslE6ZqsvGuhIJya1HAFy_pf9jmPswufXp5y5m2j3LQ7fcGh8p7cFBWM2mKycjpY420dbuiQcu0MPx2qqkrJuVDx4E9mcXBsdqVUufEnqTPzKnwwHS_mOst9t3kBTXLPg'

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="Authorization", raw_value=bytes(jwt_token, 'utf-8'))
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    request_headers = service_pb2.HttpHeaders(headers=header_map,
                                              end_of_stream=True)

    decoded_items = [('decoded-sub', '1234567890'),
                     ('decoded-name', 'John Doe'),
                     ('decoded-admin', 'True'),
                     ('decoded-iat', '1712776761'),
                     ('decoded-exp', '2075656761')]

    value = make_request(stub, request_headers=request_headers)
    assert value.HasField('request_headers')
    assert value.request_headers == add_header_mutation(
      add=decoded_items,
      clear_route_cache=True)