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

import time
import grpc
import pytest
import datetime

from http.server import HTTPServer, BaseHTTPRequestHandler
from grpc import ServicerContext

import service_callout
import service_pb2
import service_pb2_grpc


class CalloutServerTest(service_callout.CalloutServer):
  def on_request_headers(self,
                         headers: service_pb2.HttpHeaders,
                         context: ServicerContext) -> service_pb2.HeadersResponse:
    'Custom processor on request headers.'
    return service_callout.add_header_mutation(
        add=[('host', 'service-extensions.com'), (':path', '/')],
        clear_route_cache=True,
    )

  def on_response_headers(self,
                          headers: service_pb2.HttpHeaders,
                          context: ServicerContext) -> service_pb2.HeadersResponse:
    'Custom processor on response headers.'
    return service_callout.add_header_mutation(
        add=[('hello', 'service-extensions')],
        remove=['foo'],
    )

  def on_request_body(self,
                      body: service_pb2.HttpBody,
                      context: ServicerContext) -> service_pb2.BodyResponse:
    'Custom processor on the request body.'
    return service_callout.add_body_mutation(body='-added-body')

  def on_response_body(self,
                       body: service_pb2.HttpBody,
                       context: ServicerContext) -> service_pb2.BodyResponse:
    'Custom processor on the response body.'
    return service_callout.add_body_mutation(
        body='new-body',
        clear_body=True
    )


def wait_till_server(server_check, timeout=10):
  expiration = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
  while not server_check() and datetime.datetime.now() < expiration:
    time.sleep(1)

@pytest.fixture(scope='class')
def setup_and_teardown() -> None:
  global server
  server = CalloutServerTest()
  try:
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    # Wait for the server to start
    wait_till_server(lambda: server.setup)
    yield
    # Stop the server
    server.close()
    thread.join(timeout=5)
  finally:
    del server

def _MakeRequest(stub: service_pb2_grpc.ExternalProcessorStub, **kwargs):
  request_iter = iter([service_pb2.ProcessingRequest(**kwargs)])
  return next(stub.Process(request_iter), None)

class TestBasicServer(object):
  @pytest.mark.usefixtures('setup_and_teardown')
  def test_basic_server_capabilites(self) -> None:
    try:
      with grpc.insecure_channel(f'0.0.0.0:{server.insecure_port}') as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)

        _body = service_pb2.HttpBody(end_of_stream=False)
        _headers = service_pb2.HttpHeaders(end_of_stream=False)
        _end_headers = service_pb2.HttpHeaders(end_of_stream=True)

        value = _MakeRequest(stub, request_body=_body, async_mode=False)
        assert value.HasField('request_body')
        assert value.request_body == service_callout.add_body_mutation(
          body='-added-body')

        value = _MakeRequest(stub, response_body=_body, async_mode=False)
        assert value.HasField('response_body')
        assert value.response_body == service_callout.add_body_mutation(
          body='new-body', clear_body=True)

        value = _MakeRequest(stub, response_headers=_headers, async_mode=False)
        assert value.HasField('response_headers')
        assert value.response_headers == service_callout.add_header_mutation(
          add=[('hello', 'service-extensions')], remove=['foo'])

        value = _MakeRequest(stub, request_headers=_headers, async_mode=False)
        assert value.HasField('request_headers')
        assert value.request_headers == service_callout.add_header_mutation(
          add=[('host', 'service-extensions.com'), (':path', '/')], 
          clear_route_cache=True)

        _MakeRequest(stub, request_headers=_end_headers, async_mode=False)
    except grpc._channel._MultiThreadedRendezvous:
      raise Exception('Setup Error: Server not ready!')

  @pytest.mark.usefixtures('setup_and_teardown')
  def test_basic_server_health_check(self) -> None:
    try:
      response = urllib.request.urlopen(
        f'http://{server.health_check_ip}:{server.health_check_port}')
      assert response.read() == b''
      assert response.getcode() == 200
    except urllib.error.URLError:
      raise Exception('Setup Error: Server not ready!')
  
  @pytest.mark.usefixtures('setup_and_teardown')
  def test_basic_server_certs(self) -> None:
    try:
      with open('../ssl_creds/root.crt', 'rb') as file:
        self.root_cert = file.read()
        file.close()
      creds = grpc.ssl_channel_credentials(self.root_cert)
      options = (('grpc.ssl_target_name_override', 'localhost',),)
      with grpc.secure_channel(f'{server.ip}:{server.port}', creds, options=options) as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)
        _end_headers = service_pb2.HttpHeaders(end_of_stream=True)
        _MakeRequest(stub, request_headers=_end_headers, async_mode=False)
    except urllib.error.URLError:
      raise Exception('Setup Error: Server not ready!')

def test_custom_server_config() -> None:
  try:
    ip = '0.0.0.0'
    port = 8444
    insecure_port = 8081
    health_check_ip = '0.0.0.0'
    health_check_port = 8001

    server = CalloutServerTest(ip=ip, port=port, insecure_port=insecure_port,
      health_check_ip=health_check_ip, health_check_port=health_check_port)
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    wait_till_server(lambda: server.setup)

    response = urllib.request.urlopen(f'http://{health_check_ip}:{health_check_port}')
    assert response.read() == b''
    assert response.getcode() == 200

    with grpc.insecure_channel(f'{ip}:{insecure_port}') as channel:
      stub = service_pb2_grpc.ExternalProcessorStub(channel)
      _end_headers = service_pb2.HttpHeaders(end_of_stream=True)
      _MakeRequest(stub, request_headers=_end_headers, async_mode=False)
    
    # Stop the server
    server.close()
    thread.join(timeout=5)
  except urllib.error.URLError:
    raise Exception('Failed to connect to the callout server.')
  except grpc._channel._MultiThreadedRendezvous:
    raise Exception('Setup Error: Server not ready!')
  finally:
    del server

def test_custom_server_no_health_check_no_insecure_port() -> None:
  try:
    server = CalloutServerTest(serperate_health_check=True,
      enable_insecure_port=False)
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    wait_till_server(lambda: server.setup)
    # Attempt to connect to the addresses that would be used for the 
    # insecure address and the health check.
    test_server_1 = HTTPServer(('0.0.0.0', 8000), BaseHTTPRequestHandler)
    test_server_2 = HTTPServer(('0.0.0.0', 8080), BaseHTTPRequestHandler)
    # Stop the server
    server.close()
    thread.join(timeout=5)
  except OSError:
    raise Exception('Expected the health check address to be unbound.')
  finally:
    del server
    del test_server_1
    del test_server_2
