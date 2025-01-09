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
Takes in service callouts and performs header and body transformations.
Bundled with an optional health check server.
Can be set up to use ssl certificates.
"""

from concurrent import futures
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
import logging
import ssl
from typing import Iterator, Union
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


def _addr_to_str(address: tuple[str, int]) -> str:
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
    address: Address that the main secure server will attempt to connect to,
      defaults to default_ip:443.
    port: If specified, overrides the port of address.
    health_check_address: The health check serving address,
      defaults to default_ip:80.
    health_check_port: If set, overrides the port of health_check_address.
    combined_health_check: If True, does not create a separate health check server.
    secure_health_check: If True, will use HTTPS as the protocol of the health check server.
      Requires cert_chain_path and private_key_path to be set.
    plaintext_address: The non-authenticated address to listen to,
      defaults to default_ip:8080.
    plaintext_port: If set, overrides the port of plaintext_address.
    disable_plaintext: If true, disables the plaintext address of the server.
    default_ip: If left None, defaults to '0.0.0.0'.
    cert_chain: PEM Certificate chain used to authenticate secure connections,
      required for secure servers.
    cert_chain_path: Relative file path to the cert_chain.
    private_key: PEM private key of the server.
    private_key_path: Relative file path pointing to a file containing private_key data.
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
      plaintext_address: tuple[str, int] | None = None,
      plaintext_port: int | None = None,
      disable_plaintext: bool = False,
      default_ip: str | None = None,
      cert_chain: bytes | None = None,
      cert_chain_path: str | None = './extproc/ssl_creds/chain.pem',
      private_key: bytes | None = None,
      private_key_path: str = './extproc/ssl_creds/privatekey.pem',
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

    self.plaintext_address: tuple[str, int] | None = None
    if not disable_plaintext:
      self.plaintext_address = plaintext_address or (default_ip, 8080)
      if plaintext_port:
        self.plaintext_address = (self.plaintext_address[0], plaintext_port)

    self.health_check_address: tuple[str, int] | None = None
    if not combined_health_check:
      self.health_check_address = health_check_address or (default_ip, 80)
      if health_check_port:
        self.health_check_address = (self.health_check_address[0],
                                     health_check_port)

    def _read_cert_file(path: str | None) -> bytes | None:
      if path:
        with open(path, 'rb') as file:
          return file.read()
      return None

    self.server_thread_count = server_thread_count
    self.secure_health_check = secure_health_check
    # Read cert data.
    self.private_key = private_key or _read_cert_file(private_key_path)
    self.cert_chain = cert_chain or _read_cert_file(cert_chain_path)

    if secure_health_check:
      if not private_key_path:
        logging.error("Secure health check requires a private_key_path.")
        return
      if not cert_chain_path:
        logging.error("Secure health check requires a cert_chain_path.")
        return
      self.health_check_ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
      self.health_check_ssl_context.load_cert_chain(certfile=cert_chain_path,
                                                    keyfile=private_key_path)

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
        self._health_check_server.socket = (
          self.health_check_ssl_context.wrap_socket(
            sock=self._health_check_server.socket,))

      logging.info('%s health check server bound to %s.', protocol,
                   _addr_to_str(self.health_check_address))
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
      callout: ProcessingRequest,
      context: ServicerContext,
  ) -> ProcessingResponse:
    """Process incomming callouts.

    Args:
        callout: The incomming callout.
        context: Stream context on the callout.

    Yields:
        ProcessingResponse: A response for the incoming callout.
    """
    if callout.HasField('request_headers'):
      match self.on_request_headers(callout.request_headers, context):
        case ImmediateResponse() as immediate_headers:
          return ProcessingResponse(immediate_response=immediate_headers)
        case HeadersResponse() | None as header_response:
          return ProcessingResponse(request_headers=header_response)
        case _:
          logging.warn("MALFORMED CALLOUT %s", callout)
    elif callout.HasField('response_headers'):
      return ProcessingResponse(response_headers=self.on_response_headers(
          callout.response_headers, context))
    elif callout.HasField('request_body'):
      match self.on_request_body(callout.request_body, context):
        case ImmediateResponse() as immediate_body:
          return ProcessingResponse(immediate_response=immediate_body)
        case BodyResponse() | None as body_response:
          return ProcessingResponse(request_body=body_response)
        case _:
          logging.warn("MALFORMED CALLOUT %s", callout)
    elif callout.HasField('response_body'):
      return ProcessingResponse(
          response_body=self.on_response_body(callout.response_body, context))
    return ProcessingResponse()

  def on_request_headers(
      self,
      headers: HttpHeaders,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> Union[None, HeadersResponse, ImmediateResponse]:
    """Process incoming request headers.

    Args:
      headers: Request headers to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional header modification object.
    """
    return None

  def on_response_headers(
      self,
      headers: HttpHeaders,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> Union[None, HeadersResponse]:
    """Process incoming response headers.

    Args:
      headers: Response headers to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional header modification object.
    """
    return None

  def on_request_body(
      self,
      body: HttpBody,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> Union[None, BodyResponse, ImmediateResponse]:
    """Process an incoming request body.

    Args:
      headers: Request body to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional body modification object.
    """
    return None

  def on_response_body(
      self,
      body: HttpBody,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> Union[None, BodyResponse]:
    """Process an incoming response body.

    Args:
      headers: Response body to process.
      context: RPC context of the incoming callout.

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
        private_key_certificate_chain_pairs=[(processor.private_key,
                                              processor.cert_chain)])
    address_str = _addr_to_str(processor.address)
    self._server.add_secure_port(address_str, server_credentials)
    self._start_msg = f'GRPC callout server started, listening on {address_str}.'
    if processor.plaintext_address:
      plaintext_address_str = _addr_to_str(processor.plaintext_address)
      self._server.add_insecure_port(plaintext_address_str)
      self._start_msg += f' (secure) and {plaintext_address_str} (plaintext)'

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
      callout_iterator: Iterable[ProcessingRequest],
      context: ServicerContext,
  ) -> Iterator[ProcessingResponse]:
    """Process the client callout."""
    for callout in callout_iterator:
      yield self._processor.process(callout, context)
