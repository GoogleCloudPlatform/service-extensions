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
import threading

from envoy.config.core.v3.base_pb2 import HeaderMap
from envoy.config.core.v3.base_pb2 import HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc
import grpc
import pytest

from extproc.example.redirect.service_callout_example import (
  CalloutServerExample as CalloutServerTest,
)
from extproc.service import callout_server
from extproc.service.callout_tools import header_immediate_response
from extproc.tests.basic_grpc_test import _make_request, _wait_till_server

# Global server variable.
server: callout_server.CalloutServer | None = None

@pytest.fixture(scope='class')
def setup_and_teardown():
  global server
  try:
    server = CalloutServerTest()
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    # Wait for the server to start
    _wait_till_server(lambda: server and server._setup)
    yield
    # Stop the server
    server.shutdown()
    thread.join(timeout=5)
  finally:
    del server

@pytest.mark.usefixtures('setup_and_teardown')
def test_header_immediate_response() -> None:
  with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header", raw_value=b"value")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    headers = service_pb2.HttpHeaders(headers=header_map,
                                            end_of_stream=True)

    response = _make_request(stub, request_headers=headers)

    assert response.HasField('immediate_response')
    assert response.immediate_response == header_immediate_response(
      status=301,
      headers=[('Location', 'http://service-extensions.com/redirect')])

