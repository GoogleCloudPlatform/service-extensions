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

from envoy.config.core.v3.base_pb2 import HeaderValueOption
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc
import pytest

from extproc.example.update_header.service_callout_example import (
  CalloutServerExample as CalloutServerTest,
)
from extproc.service import callout_tools
from extproc.tests.basic_grpc_test import (
  get_insecure_channel,
  insecure_kwargs,
  make_request,
  setup_server,
)


# Import the setup server test fixture.
_ = setup_server
_local_test_args = {"kwargs": insecure_kwargs, "test_class": CalloutServerTest}


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_append_action(server: CalloutServerTest) -> None:
  """Test the request and response functionality of the server."""

  with get_insecure_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    headers = service_pb2.HttpHeaders(end_of_stream=False)
    end_headers = service_pb2.HttpHeaders(end_of_stream=True)

    value = make_request(stub, response_headers=headers, observability_mode=False)
    assert value.HasField('response_headers')
    assert value.response_headers == callout_tools.add_header_mutation(
        add=[('header-response', 'response-new-value')],
        append_action=HeaderValueOption.HeaderAppendAction.
        OVERWRITE_IF_EXISTS_OR_ADD)

    value = make_request(stub, request_headers=headers, observability_mode=False)
    assert value.HasField('request_headers')
    assert value.request_headers == callout_tools.add_header_mutation(
        add=[('header-request', 'request-new-value')],
        append_action=HeaderValueOption.HeaderAppendAction.
        OVERWRITE_IF_EXISTS_OR_ADD,
        clear_route_cache=True)

    make_request(stub, request_headers=end_headers, observability_mode=False)
