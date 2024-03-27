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

from extproc.example.add_custom_response.service_callout_example import (
    CalloutServerExample as CalloutServerTest,)
from extproc.service import callout_server
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
def test_mock_request_header_handling() -> None:
  with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header-check", raw_value=b"true")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    mock_headers = service_pb2.HttpHeaders(headers=header_map,
                                           end_of_stream=True)

    response = _make_request(stub, request_headers=mock_headers)

    assert response.HasField('request_headers')
    assert any(header.header.key == "Mock-Response" for header in
               response.request_headers.response.header_mutation.set_headers)


@pytest.mark.usefixtures('setup_and_teardown')
def test_mock_response_header_handling() -> None:
  with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header-check", raw_value=b"true")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    mock_headers = service_pb2.HttpHeaders(headers=header_map,
                                           end_of_stream=True)

    response = _make_request(stub, response_headers=mock_headers)

    assert response.HasField('response_headers')
    assert any(header.header.key == "Mock-Response" for header in
               response.response_headers.response.header_mutation.set_headers)


@pytest.mark.usefixtures('setup_and_teardown')
def test_mock_request_body_handling() -> None:

  with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    mock_body = service_pb2.HttpBody(body=b"body-check")
    response = _make_request(stub, request_body=mock_body)

    assert response.HasField('request_body')
    assert response.request_body.response.body_mutation.body == b"Mocked-Body"


@pytest.mark.usefixtures('setup_and_teardown')
def test_mock_response_body_handling() -> None:

  with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    mock_body = service_pb2.HttpBody(body=b"body-check")
    response = _make_request(stub, response_body=mock_body)

    assert response.HasField('response_body')
    assert response.response_body.response.body_mutation.body == b"Mocked-Body"


@pytest.mark.usefixtures('setup_and_teardown')
def test_header_validation_failure() -> None:
  with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    # Construct the HeaderMap
    header_map = HeaderMap()
    header_value = HeaderValue(key="header-check", raw_value=b"")
    header_map.headers.extend([header_value])

    # Construct HttpHeaders with the HeaderMap
    request_headers = service_pb2.HttpHeaders(headers=header_map,
                                              end_of_stream=True)

    # Use request_headers in the request
    with pytest.raises(grpc.RpcError) as e:
      _make_request(stub, request_headers=request_headers)
    assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.usefixtures('setup_and_teardown')
def test_body_validation_failure() -> None:
  with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
    stub = service_pb2_grpc.ExternalProcessorStub(channel)

    request_body = service_pb2.HttpBody(body=b"bad-body")

    with pytest.raises(grpc.RpcError) as e:
      _make_request(stub, request_body=request_body)
    assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED