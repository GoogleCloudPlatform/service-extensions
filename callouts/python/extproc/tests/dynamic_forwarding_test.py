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
from __future__ import print_function

from extproc.service import callout_tools
from envoy.config.core.v3.base_pb2 import HeaderMap
from envoy.config.core.v3.base_pb2 import HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc
import pytest

from extproc.example.dynamic_forwarding.service_callout_example import (
    CalloutServerExample as CalloutServerTest)
from extproc.tests.basic_grpc_test import (
    make_request,
    setup_server,
    get_plaintext_channel,
    default_kwargs
)

# Import the setup server test fixture.
_ = setup_server
_local_test_args = {"kwargs": default_kwargs, "test_class": CalloutServerTest}


@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_request_headers_dynamic_metadata(server: CalloutServerTest) -> None:
  """Test the dynamic metadata response from the server."""
  with get_plaintext_channel(server) as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    def make_test_headers(host_value: bytes) -> service_pb2.HttpHeaders:
      return service_pb2.HttpHeaders(headers=HeaderMap(
          headers=[HeaderValue(key='ip-to-return', raw_value=host_value)]),
                                     end_of_stream=False)
    first_ip = make_test_headers(b'10.1.10.2')
    second_ip = make_test_headers(b'10.1.10.3')
    no_headers = service_pb2.HttpHeaders(end_of_stream=False)
    end_headers = service_pb2.HttpHeaders(end_of_stream=True)

    value = make_request(stub, request_headers=first_ip)
    expected_metadata = callout_tools.build_dynamic_forwarding_metadata('10.1.10.2',80)
    assert value.dynamic_metadata == expected_metadata
    value = make_request(stub, request_headers=second_ip)
    expected_metadata = callout_tools.build_dynamic_forwarding_metadata('10.1.10.3',80)
    assert value.dynamic_metadata == expected_metadata
    value = make_request(stub, request_headers=no_headers)
    expected_metadata = callout_tools.build_dynamic_forwarding_metadata('10.1.10.4',80)
    assert value.dynamic_metadata == expected_metadata

    make_request(stub, request_headers=end_headers)

