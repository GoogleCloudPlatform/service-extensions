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

from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc
import pytest

from extproc.example.add_body.service_callout_example import (
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
def test_mock_request_body_handling(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    mock_body = service_pb2.HttpBody(body=b"inital-body")
    response = make_request(stub, request_body=mock_body)

    assert response.request_body.response.body_mutation.body == b"inital-body-added-request-body"


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_mock_response_body_handling(server: CalloutServerTest) -> None:
  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    mock_body = service_pb2.HttpBody(body=b"inital-body")
    response = make_request(stub, response_body=mock_body)

    assert response.response_body.response.body_mutation.body == b"inital-body-added-response-body"
