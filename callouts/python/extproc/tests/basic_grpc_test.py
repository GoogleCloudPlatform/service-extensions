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
from typing import Iterator, Callable, Any, Mapping
import urllib.error
import urllib.request
import ssl

from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingRequest
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpBody
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import ExternalProcessorStub
import grpc
import pytest

from extproc.example.basic_callout_server import (BasicCalloutServer as
                                                  CalloutServerTest)
from extproc.service.callout_server import CalloutServer, addr_to_str
from extproc.service.callout_tools import add_body_mutation, add_header_mutation


class ServerSetupException(Exception):
  pass


class NoResponseError(Exception):
  pass


# Replace the default ports of the server so that they do not clash with running programs.
default_kwargs: dict = {
    'address': ('0.0.0.0', 8443),
    'health_check_address': ('0.0.0.0', 8080)
}
# Arguments for running an insecure server alongside the secure grpc.
insecure_kwargs: dict = default_kwargs | {'insecure_address': ('0.0.0.0', 8000)}
_local_test_args: dict = {
    "kwargs": insecure_kwargs,
    "test_class": CalloutServerTest
}


def get_insecure_channel(server: CalloutServer) -> grpc.Channel:
  """From a CalloutServer get the insecure address and create a grpc channel to it.

  Args:
      server : Server to connect to.
  Returns:
      grpc.Channel: Open channel to the server.
  """
  addr = server.insecure_address
  return grpc.insecure_channel(addr_to_str(addr) if addr else '')


def wait_till_server(server_check: Callable[[], bool], timeout: int = 10):
  """Wait untill the `server_check` function returns true.

  Used for blocking until the server reaches a given state.
  Times out after a given time.

  Args:
      server_check : Function to check.
      timeout : Wait time. Defaults to 10.
  """
  expiration = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
  while not server_check() and datetime.datetime.now() < expiration:
    time.sleep(1)


def _start_server(server: CalloutServer) -> threading.Thread:
  # Start the server in a background thread
  thread = threading.Thread(target=server.run)
  thread.daemon = True
  thread.start()
  # Wait for the server to start
  wait_till_server(lambda: server._setup)
  return thread


def _stop_server(server: CalloutServer, thread: threading.Thread):
  # Stop the server
  server.shutdown()
  thread.join(timeout=5)


@pytest.fixture(scope='class', name='server')
def setup_server(request) -> Iterator[CalloutServer]:
  """Set up basic CalloutServer.

  Takes in two optional pytest parameters.
  'kwargs': Arguments passed into the server constructor. 
    Default is the value of default_kwargs.
  'test_class': Class to use when constructing the server.
    Default is the base CalloutServer.

  Yields:
      Iterator[CalloutServer]: The server to test with.
  """
  params: dict = request.param or {'kwargs': {}, 'test_class': None}
  kwargs: Mapping[str, Any] = default_kwargs | params['kwargs']
  # Either use the provided class or create a server using the default CalloutServer class.
  server = (params['test_class'] or CalloutServer)(**kwargs)
  try:
    thread = _start_server(server)
    yield server
    _stop_server(server, thread)
  finally:
    del server


def make_request(stub: ExternalProcessorStub, **kwargs) -> ProcessingResponse:
  """Make a request to the server.

  Args:
    stub: The server stub.
    **kwargs: Parameters to input into the ProcessingRequest.

  Returns: The response returned from the server.
  """
  request_iter = iter([ProcessingRequest(**kwargs)])
  responses = stub.Process(request_iter)
  # Get the first response
  for response in responses:
    return response
  raise NoResponseError("Response not found.")


class TestBasicServer(object):
  """Unmodified server functionality test."""

  @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
  def test_basic_server_capabilites(self, server: CalloutServerTest) -> None:
    """Test the request and response functionality of the server."""
    root_cert: bytes = b''
    with open('./extproc/ssl_creds/root.crt', 'rb') as file:
      root_cert = file.read()
      file.close()
    creds = grpc.ssl_channel_credentials(root_cert)
    options = ((
        'grpc.ssl_target_name_override',
        'localhost',
    ),)
    with grpc.secure_channel(f'{addr_to_str(server.address)}',
                             creds,
                             options=options) as channel:
      stub = ExternalProcessorStub(channel)

      body = HttpBody(end_of_stream=False)
      headers = HttpHeaders(end_of_stream=False)
      end_headers = HttpHeaders(end_of_stream=True)

      value = make_request(stub, request_body=body)
      assert value.HasField('request_body')
      assert value.request_body == add_body_mutation(body='-added-body')

      value = make_request(stub, response_body=body)
      assert value.HasField('response_body')
      assert value.response_body == add_body_mutation(clear_body=True)

      value = make_request(stub, response_headers=headers)
      assert value.HasField('response_headers')
      assert value.response_headers == add_header_mutation(
          add=[('hello', 'service-extensions')])

      value = make_request(stub, request_headers=headers)
      assert value.HasField('request_headers')
      assert value.request_headers == add_header_mutation(
          add=[(':host', 'service-extensions.com'), (':path', '/'),
               ('header-request', 'request')],
          clear_route_cache=True,
          remove=['foo'])

      make_request(stub, request_headers=end_headers)
      channel.close()

  @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
  def test_basic_server_health_check(self, server: CalloutServerTest) -> None:
    """Test that the health check sub server returns the expected 200 code."""
    assert server.health_check_address is not None
    response = urllib.request.urlopen(
        f'http://{addr_to_str(server.health_check_address)}')
    assert not response.read()
    assert response.getcode() == 200


_secure_test_args: dict = {
    "kwargs": insecure_kwargs | {
        'secure_health_check': True
    },
    "test_class": CalloutServerTest
}


@pytest.mark.parametrize('server', [_secure_test_args], indirect=True)
def test_https_health_check(server: CalloutServerTest) -> None:
  """Test that the health check sub server returns the expected 200 code."""
  assert server.health_check_address is not None
  ssl_context = ssl.create_default_context()
  ssl_context.check_hostname = False
  ssl_context.verify_mode = ssl.CERT_NONE
  response = urllib.request.urlopen(
      f'https://{addr_to_str(server.health_check_address)}',
      context=ssl_context)
  assert not response.read()
  assert response.getcode() == 200


def test_custom_server_config() -> None:
  """Test that port customization connects correctly."""
  server: CalloutServer | None = None
  try:
    ip = '0.0.0.0'
    port = 8444
    insecure_port = 8081
    health_check_port = 8001

    server = test_server = CalloutServerTest(
        address=(ip, port),
        insecure_address=(ip, insecure_port),
        health_check_address=(ip, health_check_port))
    # Start the server in a background thread
    thread = threading.Thread(target=test_server.run)
    thread.daemon = True
    thread.start()
    wait_till_server(lambda: test_server._setup)

    response = urllib.request.urlopen(f'http://{ip}:{health_check_port}')
    assert response.read() == b''
    assert response.getcode() == 200

    with grpc.insecure_channel(f'{ip}:{insecure_port}') as channel:
      stub = ExternalProcessorStub(channel)
      value = make_request(stub,
                           response_headers=HttpHeaders(end_of_stream=True))
      assert value.HasField('response_headers')
      assert value.response_headers == add_header_mutation(
          add=[('hello', 'service-extensions')])

    # Stop the server
    test_server.shutdown()
    thread.join(timeout=5)
  except urllib.error.URLError as ex:
    raise ServerSetupException(
        'Failed to connect to the callout server.') from ex
  finally:
    del server


_no_health_args: dict = {
    "kwargs": insecure_kwargs | {
        'combined_health_check': True
    },
    "test_class": CalloutServerTest
}


@pytest.mark.parametrize('server', [_no_health_args], indirect=True)
def test_custom_server_no_health_check(server: CalloutServerTest) -> None:
  """Test that the server only conects to the specified addresses.

  The server should not connect to the health check port if its disabled 
  in the setup config.
  """
  address = _local_test_args['kwargs']['health_check_address']
  # Connect to the default health check address to confirm the port is opwn.
  test_server = HTTPServer(address, BaseHTTPRequestHandler)
  del test_server
  assert server._health_check_server is None
