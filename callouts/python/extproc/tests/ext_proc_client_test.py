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
from envoy.service.ext_proc.v3.external_processor_pb2 import (
  ProcessingRequest,
  ProcessingResponse,
)

from google.protobuf.json_format import MessageToJson
import pytest

from extproc.example.basic_callout_server import (
  BasicCalloutServer as CalloutServerTest,
)

from envoy.service.ext_proc.v3.external_processor_pb2 import HttpBody
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from extproc.example.ext_proc_client import make_json_request
from extproc.tests.basic_grpc_test import (
  setup_server,
  default_kwargs,
)

from extproc.service.callout_tools import (
  add_body_mutation,
  add_header_mutation,
)

# Import the setup server test fixture.
_ = setup_server
_local_test_args = {'kwargs': default_kwargs, 'test_class': CalloutServerTest}


def make_request_str(
  request: str, addr: tuple[str, int]
) -> ProcessingResponse:
  return next(make_json_request([request], addr))


def make_request(
  request: ProcessingRequest, addr: tuple[str, int]
) -> ProcessingResponse:
  return make_request_str(MessageToJson(request), addr)


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_empty_data(server: CalloutServerTest) -> None:
  assert server.plaintext_address
  response = make_request_str('{}', server.plaintext_address)
  assert response == ProcessingResponse()


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_basic_callouts(server: CalloutServerTest) -> None:
  addr = server.plaintext_address
  assert addr
  body = HttpBody(end_of_stream=False)
  headers = HttpHeaders(end_of_stream=False)

  response = make_request(ProcessingRequest(request_body=body), addr)
  assert response.request_body == add_body_mutation(body='replaced-body')

  response = make_request(ProcessingRequest(response_body=body), addr)
  assert response.response_body == add_body_mutation(clear_body=True)

  response = make_request(ProcessingRequest(request_headers=headers), addr)
  assert response.request_headers == add_header_mutation(
    add=[
      (':authority', 'service-extensions.com'),
      (':path', '/'),
      ('header-request', 'request'),
    ],
    remove=['foo'],
    clear_route_cache=True,
  )

  response = make_request(ProcessingRequest(response_headers=headers), addr)
  assert response.response_headers == add_header_mutation(
    add=[('hello', 'service-extensions')]
  )


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_string_sanity_check(server: CalloutServerTest) -> None:
  addr = server.plaintext_address
  assert addr
  response = make_request_str('{"requestBody": {}}', addr)
  assert response.request_body == add_body_mutation(body='replaced-body')


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_repeated_requests(server: CalloutServerTest) -> None:
  addr = server.plaintext_address
  assert addr
  responses = list(
    make_json_request(['{"requestBody": {}}', '{"responseBody": {}}'], addr)
  )
  assert responses[0].request_body == add_body_mutation(body='replaced-body')
  assert responses[1].response_body == add_body_mutation(clear_body=True)


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_secure_request(server: CalloutServerTest) -> None:
  responses = list(
    make_json_request(
      ['{"requestBody": {}}', '{"responseBody": {}}'],
      server.address,
      key='./extproc/ssl_creds/chain.pem',
    )
  )
  assert responses[0].request_body == add_body_mutation(body='replaced-body')
