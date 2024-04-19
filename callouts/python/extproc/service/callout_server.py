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
from typing import Iterator
from typing import Iterable

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
    port: If specified, overides the port of the address.
      If no address is set, defaults to default_ip.
    health_check_address: The health check serving address.
    health_check_port: If set, overides the port of the health_check_address.
      If no address is set, defaults to default_ip.
    combined_health_check: If True, does not create seperate health check server. 
    insecure_address: If specified, the server will also listen on this, 
      non-authenticated, address.
    insecure_port: If set, overides the port of the insecure_address.
      If no address is set, defaults to default_ip.
    default_ip: If left None, defaults to '0.0.0.0'. 
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
      port: int | None = None,
      health_check_address: tuple[str, int] | None = None,
      health_check_port: int | None = None,
      combined_health_check: bool = False,
      secure_health_check: bool = False,
      insecure_address: tuple[str, int] | None = None,
      insecure_port: int | None = None,
      default_ip: str | None = None,
      cert_path: str = './extproc/ssl_creds/localhost.crt',
      cert_key_path: str = './extproc/ssl_creds/localhost.key',
      public_key_path: str = './extproc/ssl_creds/publickey.pem',
      server_thread_count: int = 2,
  ):
    self._setup = False
    self._shutdown = False
    self._closed = False
    self._health_check_server: HTTPServer | None = None
    default_ip = default_ip or '0.0.0.0'

    self.address: tuple[str, int] = address or (default_ip, 443)
    if port:
      self.address = (self.address[0], port)

    self.insecure_address: tuple[str, int] | None = insecure_address
    if insecure_port:
      ip = self.insecure_address[0] if self.insecure_address else default_ip
      self.insecure_address = (ip, insecure_port)

    self.health_check_address: tuple[str, int] | None = None
    if not combined_health_check:
      self.health_check_address = health_check_address or (default_ip, 80)
      if health_check_port:
        self.health_check_address = (self.health_check_address[0],
                                     health_check_port)

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
    self.public_key_path = public_key_path
    with open(public_key_path, 'rb') as file:
      self.public_key = file.read()
      file.close()

    self._callout_server = _GRPCCalloutService(self)

  def run(self) -> None:
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

  def _start_servers(self) -> None:
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
    self._callout_server.start()

  def _stop_servers(self) -> None:
    """Close the sockets of all servers, and trigger shutdowns."""
    if self._health_check_server:
      self._health_check_server.server_close()
      self._health_check_server.shutdown()
      logging.info('Health check server stopped.')

    if self._callout_server:
      self._callout_server.stop()

  def _loop_server(self) -> None:
    """Loop server forever, calling shutdown will cause the server to stop."""

    # We chose the main serving thread based on what server configuration
    # was requested. Defaults to the health check thread.
    if self._health_check_server:
      logging.info("Health check server started.")
      self._health_check_server.serve_forever()
    else:
      # If the only server requested is a grpc callout server, we wait on the grpc server.
      self._callout_server.loop()

  def shutdown(self) -> None:
    """Tell the server to shutdown, ending all serving threads."""
    if self._health_check_server:
      self._health_check_server.shutdown()
    if self._callout_server:
      self._callout_server.stop()

  def process(
      self,
      request: ProcessingRequest,
      context: ServicerContext,
  ) -> ProcessingResponse:
    """Process incomming callout requests.

    Args:
        request: The incomming request.
        context: Stream context on requests.

    Yields:
        ProcessingResponse: A response for the incoming request.
    """
    if request.HasField('request_headers'):
      match self.on_request_headers(request.request_headers, context):
        case ImmediateResponse() as immediate_headers:
          return ProcessingResponse(immediate_response=immediate_headers)
        case HeadersResponse() | None as header_response:
          return ProcessingResponse(request_headers=header_response)
        case _:
          logging.warn("MALFORMED REQUEST %s", request)
    elif request.HasField('response_headers'):
      return ProcessingResponse(response_headers=self.on_response_headers(
          request.response_headers, context))
    elif request.HasField('request_body'):
      match self.on_request_body(request.request_body, context):
        case ImmediateResponse() as immediate_body:
          return ProcessingResponse(immediate_response=immediate_body)
        case BodyResponse() | None as body_response:
          return ProcessingResponse(request_body=body_response)
        case _:
          logging.warn("MALFORMED REQUEST %s", request)
    elif request.HasField('response_body'):
      return ProcessingResponse(
          response_body=self.on_response_body(request.response_body, context))
    return ProcessingResponse()

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
    self._processor = processor
    self._server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=processor.server_thread_count))
    add_ExternalProcessorServicer_to_server(self, self._server)
    server_credentials = grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(processor.cert_key,
                                              processor.cert)])
    address_str = addr_to_str(processor.address)
    self._server.add_secure_port(address_str, server_credentials)
    self._start_msg = f'GRPC callout server started, listening on {address_str}.'
    if processor.insecure_address:
      insecure_str = addr_to_str(processor.insecure_address)
      self._server.add_insecure_port(insecure_str)
      self._start_msg += f' (secure) and {insecure_str} (insecure)'

  def stop(self) -> None:
    self._server.stop(grace=10)
    self._server.wait_for_termination(timeout=10)
    logging.info('GRPC server stopped.')

  def loop(self) -> None:
    self._server.wait_for_termination()

  def start(self) -> None:
    self._server.start()
    logging.info(self._start_msg)

  def Process(
      self,
      request_iterator: Iterable[ProcessingRequest],
      context: ServicerContext,
  ) -> Iterator[ProcessingResponse]:
    """Process the client request."""
    for request in request_iterator:
      yield self._processor.process(request, context)