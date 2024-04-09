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
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingRequest
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import ExternalProcessorStub
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


def make_request_with_metadata(stub: ExternalProcessorStub, metadata: list[tuple[str, str]], **kwargs) -> ProcessingResponse:
  """Make a request to the server.

  Args:
    stub: The server stub.
    **kwargs: Parameters to input into the ProcessingRequest.
    metadata: A list of metadata key-value pairs to send with the request.

  Returns: The response returned from the server.
  """
  request_iter = iter([ProcessingRequest(**kwargs)])
  return next(stub.Process(request_iter, metadata=metadata))


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_jwt_auth_rs256_failure(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header-rs", raw_value=b"")
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

    jwt_token = 'Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjY4Mzc1NywiZXhwIjoyMDc1NTYzNzU3fQ.eN4mB7iKBXFjqH-a-R5xyD0ZAT69UGlRx_DKYx2ehVG_JBOoEaVWxjyD8vVriuu1lOQ49WKzqIm5dGY8O-ccobWYZ38cmn69VfhSrqBQ3NIjD2cJer37H-FdTkqgiDtiRdg_rkxGRe0vznfoGQaXwjBnvRZgVpmWj4W2LLAbNN606Nl-boLDLodsDyPJEnD_jN7EOFjrpqGWLVosNnJmwaQfmCILz_q8t5BJe7ysr75xkBv5tta0HTpDoWsDmIR-qFNbpFHx_otgvabv4IE_X6yPBcjTupkMPw_DyVhm7tEBScXTQX-uT6NRJQ7BBaNEDPktkeCUm4QsIRVthen3xw'
    custom_metadata = [('authorization', jwt_token)]

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header-rs", raw_value=b"value")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    request_headers = service_pb2.HttpHeaders(headers=header_map,
                                              end_of_stream=True)

    decoded_items = [('decoded-sub', '1234567890'),
                     ('decoded-name', 'John Doe'),
                     ('decoded-admin', 'True'),
                     ('decoded-iat', '1712683757'),
                     ('decoded-exp', '2075563757')]

    value = make_request_with_metadata(stub, request_headers=request_headers, metadata=custom_metadata, async_mode=False)
    assert value.HasField('request_headers')
    assert value.request_headers == add_header_mutation(
      add=decoded_items,
      clear_route_cache=True)


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_jwt_auth_hs256_failure(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header-hmac", raw_value=b"")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    request_headers = service_pb2.HttpHeaders(headers=header_map,
                                              end_of_stream=True)

    # Use request_headers in the request
    with pytest.raises(grpc.RpcError) as e:
      make_request(stub, request_headers=request_headers)
    assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED

@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_jwt_auth_hs256_success(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    jwt_token = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjM1MTk5NywiZXhwIjoyMDc1MjMxOTk3fQ.sheYamXYaJsqRhTv1g_tyTbP9D7Q8Q3ANh2AgH7l46Q'
    custom_metadata = [('authorization', jwt_token)]

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header-hmac", raw_value=b"value")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    request_headers = service_pb2.HttpHeaders(headers=header_map,
                                              end_of_stream=True)

    decoded_items = [('decoded-sub', '1234567890'),
                     ('decoded-name', 'John Doe'),
                     ('decoded-admin', 'True'),
                     ('decoded-iat', '1712351997'),
                     ('decoded-exp', '2075231997')]

    value = make_request_with_metadata(stub, request_headers=request_headers, metadata=custom_metadata, async_mode=False)
    assert value.HasField('request_headers')
    assert value.request_headers == add_header_mutation(
      add=decoded_items,
      clear_route_cache=True)