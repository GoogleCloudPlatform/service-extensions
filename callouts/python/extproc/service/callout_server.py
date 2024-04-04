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
"""SDK for service callout servers.

Provides a customizeable, out of the box, service callout server.
Takes in service callout requests and performs header and body transformations.
Bundled with an optional health check server.
Can be set up to use ssl certificates.
"""

from concurrent import futures
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
import logging
import ssl
from ssl import SSLContext
from typing import Iterator, Literal

from envoy.service.ext_proc.v3.external_processor_pb2 import HttpBody
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from envoy.service.ext_proc.v3.external_processor_pb2 import BodyResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import ImmediateResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingRequest
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingResponse
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import (
    add_ExternalProcessorServicer_to_server,)
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import (
    ExternalProcessorServicer,)
import grpc
from grpc import ServicerContext


def addr_to_str(address: tuple[str, int]) -> str:
  """Take in an address tuple and returns a formated ip string.

  Args:
      address: Address to transform.

  Returns:
      str: f'{address[0]}:{address[1]}'
  """
  return f'{address[0]}:{address[1]}'


class HealthCheckService(BaseHTTPRequestHandler):
  """Server for responding to health check pings."""

  def do_GET(self) -> None:
    """Returns an empty page with 200 status code."""
    self.send_response(200)
    self.end_headers()


class CalloutServer:
  """Server wrapper for managing callout servers and processing callouts.

  Attributes:
    address: Address that the main secure server will attempt to connect to.
    health_check_address: The health check serving address. If False
      no health check server will be started.
    insecure_address: If specified, the server will also listen on this, 
      non-authenticated, address.
    cert: If speficied, certificate used to authenticate the main grpc service
      for secure htps and http connections. If unspecified will attempt to
      load data from a file pointed to by the cert_path.
    cert_path: Relative file path pointing to the main services certificate,
      also used for the health check, if specified.
    cert_key_path: Relative file path pointing to the public key of the 
      grpc certificate.
    server_thread_count: Threads allocated to the main grpc service.
  """

  def __init__(
      self,
      address: tuple[str, int] | None = None,
      health_check_address: tuple[str, int] | Literal[False] | None = None,
      secure_health_check: bool = False,
      insecure_address: tuple[str, int] | None = None,
      cert_path: str = './extproc/ssl_creds/localhost.crt',
      cert_key_path: str = './extproc/ssl_creds/localhost.key',
      server_thread_count: int = 2,
  ):
    self._setup = False
    self._shutdown = False
    self._closed = False

    self._health_check_server: HTTPServer | None = None
    self._callout_server: grpc.Server | None = None

    self.address: tuple[str, int] = address or ('0.0.0.0', 443)
    self.insecure_address: tuple[str, int] | None = insecure_address
    self.health_check_address: tuple[str, int] | None = None
    if health_check_address is not False:
      self.health_check_address = (health_check_address or ('0.0.0.0', 80))
    self.server_thread_count = server_thread_count
    self.secure_health_check = secure_health_check
    # Read cert data.
    self.cert_path = cert_path
    with open(cert_path, 'rb') as file:
      self.cert = file.read()
      file.close()
    self.cert_key_path = cert_key_path
    with open(cert_key_path, 'rb') as file:
      self.cert_key = file.read()
      file.close()

  def run(self):
    """Start all requested servers and listen for new connections; blocking."""
    self._start_servers()
    self._setup = True
    try:
      self._loop_server()
    except KeyboardInterrupt:
      logging.info('Server interrupted')
    finally:
      self._stop_servers()
      self._closed = True

  def _start_servers(self):
    """Start the requested servers."""
    if self.health_check_address:
      self._health_check_server = HTTPServer(self.health_check_address,
                                             HealthCheckService)
      protocol = 'HTTP'
      if self.secure_health_check:
        protocol = 'HTTPS'
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=self.cert_path,
                                    keyfile=self.cert_key_path)
        self._health_check_server.socket = ssl_context.wrap_socket(
            sock=self._health_check_server.socket,)

      logging.info('%s health check server bound to %s.', protocol,
                   addr_to_str(self.health_check_address))

    self._callout_server = _GRPCCalloutService.start_callout_service(self)

  def _stop_servers(self):
    """Close the sockets of all servers, and trigger shutdowns."""
    if self._health_check_server:
      self._health_check_server.server_close()
      self._health_check_server.shutdown()
      logging.info('Health check server stopped.')

    if self._callout_server:
      self._callout_server.stop(grace=10).wait()
    logging.info('GRPC server stopped.')

  def _loop_server(self):
    """Loop server forever, calling shutdown will cause the server to stop."""

    # We chose the main serving thread based on what server configuration
    # was requested. Defaults to the health check thread.
    if self._health_check_server:
      logging.info("Health check server started.")
      self._health_check_server.serve_forever()
    else:
      # If the only server requested is a grpc callout server, we loop
      # this main thread while the server is running.
      while not self._shutdown:
        pass

  def shutdown(self):
    """Tell the server to shutdown, ending all serving threads."""
    if self._health_check_server:
      self._health_check_server.shutdown()
    self._shutdown = True

  def process(
      self,
      request_iterator: Iterator[ProcessingRequest],
      context: ServicerContext,
  ) -> Iterator[ProcessingResponse]:
    """Process incomming callout requests.

    Args:
        request_iterator: Provides incomming request on next().
        context: Stream context on requests.

    Yields:
        Iterator[ProcessingResponse]: Responses per request.
    """
    for request in request_iterator:
      if request.HasField('request_headers'):
        match self.on_request_headers(request.request_headers, context):
          case ImmediateResponse() as immediate_headers:
            yield ProcessingResponse(immediate_response=immediate_headers)
          case HeadersResponse() | None as header_response:
            yield ProcessingResponse(request_headers=header_response)
      if request.HasField('response_headers'):
        yield ProcessingResponse(response_headers=self.on_response_headers(
            request.response_headers, context))
      if request.HasField('request_body'):
        match self.on_request_body(request.request_body, context):
          case ImmediateResponse() as immediate_body:
            yield ProcessingResponse(immediate_response=immediate_body)
          case BodyResponse() | None as body_response:
            yield ProcessingResponse(request_body=body_response)
      if request.HasField('response_body'):
        yield ProcessingResponse(
            response_body=self.on_response_body(request.response_body, context))

  def on_request_headers(
      self,
      headers: HttpHeaders,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | HeadersResponse | ImmediateResponse:
    """Process incoming request headers.

    Args:
      headers: Request headers to process.
      context: RPC context of the incoming request.

    Returns:
      Optional header modification object.
    """
    return None

  def on_response_headers(
      self,
      headers: HttpHeaders,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | HeadersResponse:
    """Process incoming response headers.

    Args:
      headers: Response headers to process.
      context: RPC context of the incoming request.

    Returns:
      Optional header modification object.
    """
    return None

  def on_request_body(
      self,
      body: HttpBody,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | BodyResponse | ImmediateResponse:
    """Process an incoming request body.

    Args:
      headers: Request body to process.
      context: RPC context of the incoming request.

    Returns:
      Optional body modification object.
    """
    return None

  def on_response_body(
      self,
      body: HttpBody,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | BodyResponse:
    """Process an incoming response body.

    Args:
      headers: Response body to process.
      context: RPC context of the incoming request.

    Returns:
      Optional body modification object.
    """
    return None


class _GRPCCalloutService(ExternalProcessorServicer):
  """GRPC based Callout server implementation."""

  def __init__(self, processor, *args, **kwargs):
    self.processor = processor

  @staticmethod
  def start_callout_service(server: CalloutServer) -> grpc.Server:
    """Setup and start a grpc callout server."""
    grpc_callout_service = _GRPCCalloutService(server)
    grpc_server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=server.server_thread_count))
    add_ExternalProcessorServicer_to_server(grpc_callout_service, grpc_server)
    server_credentials = grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(server.cert_key, server.cert)])
    address_str = addr_to_str(server.address)
    grpc_server.add_secure_port(address_str, server_credentials)
    start_msg = f'GRPC callout server started, listening on {address_str}.'

    if server.insecure_address:
      insecure_str = addr_to_str(server.insecure_address)
      grpc_server.add_insecure_port(insecure_str)
      start_msg += f' (secure) and {insecure_str} (insecure)'

    grpc_server.start()
    logging.info(start_msg)
    return grpc_server

  def Process(
      self,
      request_iterator: Iterator[ProcessingRequest],
      context: ServicerContext,
  ) -> Iterator[ProcessingResponse]:
    """Process the client request."""
    return self.processor.process(request_iterator, context)