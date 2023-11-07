# Copyright 2023 Google LLC.
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
import urllib.request

import grpc
import pytest

from grpc import ServicerContext

import service_callout
import service_pb2
import service_pb2_grpc


def get_requests_stream() -> service_pb2.ProcessingRequest:
  _stream_headers = service_pb2.HttpHeaders(end_of_stream=False)
  _end_headers = service_pb2.HttpHeaders(end_of_stream=True)

  request = service_pb2.ProcessingRequest(request_headers=_stream_headers, async_mode=False)
  yield request
  request = service_pb2.ProcessingRequest(response_headers=_stream_headers, async_mode=False)
  yield request
  request = service_pb2.ProcessingRequest(request_headers=_end_headers, async_mode=False)
  yield request


class CalloutServerTest(service_callout.CalloutServer):
  def on_request_headers(self,
                         request: service_pb2.ProcessingRequest,
                         context: ServicerContext) -> service_pb2.HeadersResponse:
    "Custom processor on request headers."
    return service_callout.add_header_mutation(
        add=[("host", "service-extensions.com"), (":path", "/")],
        clear_route_cache=True,
    )

  def on_response_headers(self,
                          request: service_pb2.ProcessingRequest,
                          context: ServicerContext) -> service_pb2.HeadersResponse:
    "Custom processor on response headers."
    return service_callout.add_header_mutation(
        add=[("hello", "service-extensions")],
        remove=["foo"],
    )

  def on_request_body(self,
                      request: service_pb2.ProcessingRequest,
                      context: ServicerContext) -> service_pb2.BodyResponse:
    "Custom processor on the request body."
    return service_callout.add_body_mutation(body="-added-body")

  def on_response_body(self,
                       request: service_pb2.ProcessingRequest,
                       context: ServicerContext) -> service_pb2.BodyResponse:
    "Custom processor on the response body."
    return service_callout.add_body_mutation(
        body="new-body",
        clear_body=True
    )


@pytest.fixture(scope="module")
def setup_and_teardown() -> None:
  global server
  try:
    server = CalloutServerTest()
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    # Wait for the server to start
    thread.join(timeout=5)
    yield
  finally:
    # Stop the server
    del thread
    del server


@pytest.mark.usefixtures("setup_and_teardown")
def test_server() -> None:
  try:
    with grpc.insecure_channel(
        f"0.0.0.0:{server.insecure_port}"
    ) as channel:
      stub = service_pb2_grpc.ExternalProcessorStub(channel)
      for response in stub.Process(get_requests_stream()):
        str_message = str(response)
        if "request_headers" in str_message:
          assert 'raw_value: "service-extensions.com"' in str_message
          assert 'key: "host"' in str_message
        elif "response_headers" in str_message:
          assert 'raw_value: "service-extensions"' in str_message
          assert 'key: "hello"' in str_message
  except grpc._channel._MultiThreadedRendezvous:
    raise Exception("Setup Error: Server not ready!")


@pytest.mark.usefixtures("setup_and_teardown")
def test_server_health_check() -> None:
  try:
    response = urllib.request.urlopen(f"http://0.0.0.0:{server.health_check_port}")
    assert response.read() == b""
    assert response.getcode() == 200
  except urllib.error.URLError:
    raise Exception("Setup Error: Server not ready!")


if __name__ == "__main__":
  # Run the gRPC service
  test_server()
