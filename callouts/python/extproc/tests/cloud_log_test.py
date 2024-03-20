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

import datetime
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
import threading
import time
import urllib.request

import grpc
from grpc import ServicerContext
import pytest
from extproc.service import callout_server
from extproc.proto import service_pb2
from extproc.proto import service_pb2_grpc

# Global server variable.
server: callout_server.CalloutServer | None = None


class CalloutServerTest(callout_server.CalloutServer):

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Custom processor on request headers."""
    return callout_server.add_header_mutation(
      add=[('header-request', 'request')],
      clear_route_cache=True
    )

  def on_request_body(
      self, body: service_pb2.HttpBody, context: ServicerContext
  ) -> service_pb2.BodyResponse:
    """Custom processor on the request body."""
    return callout_server.add_body_mutation(body='-added-body')


def wait_till_server(server_check, timeout=10):
  expiration = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
  while not server_check() and datetime.datetime.now() < expiration:
    time.sleep(1)


@pytest.fixture(scope='class')
def setup_and_teardown() -> None:
  global server
  try:
    server = CalloutServerTest()
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    # Wait for the server to start
    wait_till_server(lambda: server._setup)
    yield
    # Stop the server
    server.shutdown()
    thread.join(timeout=5)
  finally:
    del server


def _MakeRequest(
    stub: service_pb2_grpc.ExternalProcessorStub, **kwargs
) -> service_pb2.ProcessingResponse:
  """Make a request to the server.

  Args:
    stub: The server stub.
    **kwargs: Parameters to input into the ProcessingRequest.

  Returns: The response returned from the server.
  """
  request_iter = iter([service_pb2.ProcessingRequest(**kwargs)])
  return next(stub.Process(request_iter), None)


class TestBasicServer(object):

  @pytest.mark.usefixtures('setup_and_teardown')
  def test_basic_server_capabilites(self) -> None:
    """Test the request and response functionality of the server."""
    try:
      with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)

        body = service_pb2.HttpBody(end_of_stream=False)
        headers = service_pb2.HttpHeaders(end_of_stream=False)
        end_headers = service_pb2.HttpHeaders(end_of_stream=True)

        value = _MakeRequest(stub, request_body=body, async_mode=False)
        assert value.HasField('request_body')
        assert value.request_body == callout_server.add_body_mutation(
            body='-added-body'
        )

        value = _MakeRequest(stub, request_headers=headers, async_mode=False)
        assert value.HasField('request_headers')
        assert value.request_headers == callout_server.add_header_mutation(
            add=[('header-request', 'request')],
            clear_route_cache=True,
        )

        _MakeRequest(stub, request_headers=end_headers, async_mode=False)
    except grpc._channel._MultiThreadedRendezvous as ex:
      raise Exception('Setup Error: Server not ready!') from ex

  @pytest.mark.usefixtures('setup_and_teardown')
  def test_basic_server_health_check(self) -> None:
    """Test that the health check sub server returns the expected 200 code."""
    try:
      response = urllib.request.urlopen(
          f'http://{server.health_check_ip}:{server.health_check_port}'
      )
      assert not response.read()
      assert response.getcode() == 200
    except urllib.error.URLError as ex:
      raise Exception('Setup Error: Server not ready!') from ex

  @pytest.mark.usefixtures('setup_and_teardown')
  def test_basic_server_certs(self) -> None:
    """Check that the server can handle secure callouts with certs."""
    try:
      with open('./extproc/ssl_creds/root.crt', 'rb') as file:
        self.root_cert = file.read()
        file.close()
      creds = grpc.ssl_channel_credentials(self.root_cert)
      options = (
          (
              'grpc.ssl_target_name_override',
              'localhost',
          ),
      )
      with grpc.secure_channel(
          f'{server.ip}:{server.port}', creds, options=options
      ) as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)
        end_headers = service_pb2.HttpHeaders(end_of_stream=True)
        _MakeRequest(stub, request_headers=end_headers, async_mode=False)
    except urllib.error.URLError as ex:
      raise Exception('Setup Error: Server not ready!') from ex


def test_custom_server_config() -> None:
  """Test that port customization connects correctly."""
  global server
  try:
    ip = '0.0.0.0'
    port = 8444
    insecure_port = 8081
    health_check_ip = '0.0.0.0'
    health_check_port = 8001

    server = CalloutServerTest(
        ip=ip,
        port=port,
        insecure_port=insecure_port,
        health_check_ip=health_check_ip,
        health_check_port=health_check_port,
    )
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    wait_till_server(lambda: server._setup)

    response = urllib.request.urlopen(
        f'http://{health_check_ip}:{health_check_port}'
    )
    assert response.read() == b''
    assert response.getcode() == 200

    with grpc.insecure_channel(f'{ip}:{insecure_port}') as channel:
      stub = service_pb2_grpc.ExternalProcessorStub(channel)
      end_headers = service_pb2.HttpHeaders(end_of_stream=True)
      _MakeRequest(stub, request_headers=end_headers, async_mode=False)

    # Stop the server
    server.shutdown()
    thread.join(timeout=5)
  except urllib.error.URLError as ex:
    raise Exception('Failed to connect to the callout server.') from ex
  except grpc._channel._MultiThreadedRendezvous as ex:
    raise Exception('Setup Error: Server not ready!') from ex
  finally:
    del server


def test_custom_server_no_health_check_no_insecure_port() -> None:
  """Test that the server only conects to the specified addresses.

  The server should not connect to the insecure port or the health check port
  if they are disabled in the setup.
  """
  global server
  test_server_1 = None
  test_server_2 = None
  try:
    server = CalloutServerTest(
        serperate_health_check=True, enable_insecure_port=False
    )
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    wait_till_server(lambda: server._setup)
    # Attempt to connect to the addresses that would be used for the
    # insecure address and the health check.
    test_server_1 = HTTPServer(('0.0.0.0', 8000), BaseHTTPRequestHandler)
    test_server_2 = HTTPServer(('0.0.0.0', 8080), BaseHTTPRequestHandler)
    # Stop the server
    server.shutdown()
    thread.join(timeout=5)
  except OSError as ex:
    raise Exception('Expected the health check address to be unbound.') from ex
  finally:
    del server
    del test_server_1
    del test_server_2


@pytest.mark.usefixtures('setup_and_teardown')
def test_header_validation_failure() -> None:
  try:
    with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
      stub = service_pb2_grpc.ExternalProcessorStub(channel)

      # Construct the HeaderMap
      header_map = service_pb2.HeaderMap()
      header_value = service_pb2.HeaderValue(key="header-check", raw_value=b"fail")
      header_map.headers.extend([header_value])

      # Construct HttpHeaders with the HeaderMap
      request_headers = service_pb2.HttpHeaders(headers=header_map, end_of_stream=True)

      # Use request_headers in the request
      with pytest.raises(grpc.RpcError) as e:
        _MakeRequest(stub, request_headers=request_headers)
      assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED
  except grpc._channel._MultiThreadedRendezvous as ex:
    raise Exception('Setup Error: Server not ready!') from ex


@pytest.mark.usefixtures('setup_and_teardown')
def test_body_validation_failure() -> None:
  try:
    with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
      stub = service_pb2_grpc.ExternalProcessorStub(channel)

      request_body = service_pb2.HttpBody(body=b"body-check")

      with pytest.raises(grpc.RpcError) as e:
        _MakeRequest(stub, request_body=request_body)
      assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED
  except grpc._channel._MultiThreadedRendezvous as ex:
    raise Exception('Setup Error: Server not ready!') from ex