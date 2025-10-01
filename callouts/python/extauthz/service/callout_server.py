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
"""SDK for service callout servers implementing ext_authz protocol.

Provides a customizable, out of the box, external authorization server.
Implements the ext_authz gRPC protocol for authorization checks.
Bundled with an optional health check server.
Can be set up to use SSL certificates.
"""

from concurrent import futures
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
import logging
import ssl
from typing import Iterator, Union
from typing import Iterable

from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.config.core.v3 import base_pb2
from envoy.type.v3 import http_status_pb2
from google.rpc import status_pb2
import grpc
from grpc import ServicerContext


def _addr_to_str(address: tuple[str, int]) -> str:
  """Convert address tuple to formatted IP string.
  
  Args:
      address: Address tuple to transform.
      
  Returns:
      Formatted string: 'address[0]:address[1]'
  """
  return f'{address[0]}:{address[1]}'


class HealthCheckService(BaseHTTPRequestHandler):
  """Server for responding to health check pings."""
  
  def do_GET(self) -> None:
    """Returns an empty page with 200 status code."""
    self.send_response(200)
    self.end_headers()


class CalloutServerAuth:
  """Base server for ext_authz callouts.
  
  Implements the Authorization service from the ext_authz protocol.
  Provides a foundation for building custom authorization servers.
  
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
      cert_chain_path: str | None = './extauthz/ssl_creds/chain.pem',
      private_key: bytes | None = None,
      private_key_path: str = './extauthz/ssl_creds/privatekey.pem',
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
      """Read certificate file from path.
      
      Args:
          path: File path to read.
          
      Returns:
          File contents as bytes or None if file not found.
      """
      if path:
        try:
          with open(path, 'rb') as file:
            return file.read()
        except FileNotFoundError:
          logging.warning(f"Certificate file not found: {path}")
          return None
      return None

    self.server_thread_count = server_thread_count
    self.secure_health_check = secure_health_check
    self.private_key = private_key or _read_cert_file(private_key_path)
    self.cert_chain = cert_chain or _read_cert_file(cert_chain_path)

    if (cert_chain_path and not self.cert_chain) or (private_key_path and not self.private_key):
      logging.warning("One or both certificate files could not be read. Secure connections will be disabled.")
      self.cert_chain = None
      self.private_key = None

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

    self._callout_server = _GRPCAuthService(self)

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
    if self._health_check_server:
      logging.info("Health check server started.")
      self._health_check_server.serve_forever()
    else:
      self._callout_server.loop()

  def shutdown(self) -> None:
    """Tell the server to shutdown, ending all serving threads."""
    if self._health_check_server:
      self._health_check_server.shutdown()
    if self._callout_server:
      self._callout_server.stop()

  def Check(self, request: auth_pb2.CheckRequest, context: ServicerContext) -> auth_pb2.CheckResponse:
    """Process incoming auth check requests.
    
    This method implements the Authorization service Check method from the ext_authz protocol.
    
    Args:
        request: The authorization check request.
        context: RPC context of the incoming call.
        
    Returns:
        CheckResponse: The authorization decision with optional modifications.
    """
    return self.on_check(request, context)

  def on_check(self, request: auth_pb2.CheckRequest, context: ServicerContext) -> auth_pb2.CheckResponse:
    """Override this method to implement custom auth logic.
    
    This is the main extension point for custom authorization logic.
    Subclasses should override this method to implement their specific
    authorization rules.
    
    Args:
        request: The authorization check request containing request attributes.
        context: RPC context of the incoming call.
        
    Returns:
        CheckResponse: The authorization decision. Default implementation allows all requests.
    """
    return auth_pb2.CheckResponse(status=status_pb2.Status(code=0))


class _GRPCAuthService(auth_pb2_grpc.AuthorizationServicer):
  """GRPC based Auth server implementation.
  
  Handles the low-level gRPC server setup and request processing.
  Delegates actual authorization logic to the parent CalloutServerAuth instance.
  """

  def __init__(self, processor, *args, **kwargs):
    self._processor = processor
    self._server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=processor.server_thread_count))
    auth_pb2_grpc.add_AuthorizationServicer_to_server(self, self._server)
    
    address_str = _addr_to_str(processor.address)
    
    if processor.cert_chain and processor.private_key:
      server_credentials = grpc.ssl_server_credentials(
          private_key_certificate_chain_pairs=[(processor.private_key,
                                                processor.cert_chain)])
      self._server.add_secure_port(address_str, server_credentials)
      self._start_msg = f'GRPC auth server started, listening on {address_str} (secure)'
      
      if processor.plaintext_address:
        plaintext_address_str = _addr_to_str(processor.plaintext_address)
        self._server.add_insecure_port(plaintext_address_str)
        self._start_msg += f' and {plaintext_address_str} (plaintext)'
    else:
      if processor.plaintext_address:
        plaintext_address_str = _addr_to_str(processor.plaintext_address)
        self._server.add_insecure_port(plaintext_address_str)
        self._start_msg = f'GRPC auth server started, listening on {plaintext_address_str} (plaintext only)'
      else:
        self._server.add_insecure_port(address_str)
        self._start_msg = f'GRPC auth server started, listening on {address_str} (plaintext only)'

  def stop(self) -> None:
    """Stop the gRPC server gracefully."""
    self._server.stop(grace=10)
    self._server.wait_for_termination(timeout=10)
    logging.info('GRPC server stopped.')

  def loop(self) -> None:
    """Wait for server termination."""
    self._server.wait_for_termination()

  def start(self) -> None:
    """Start the gRPC server."""
    self._server.start()
    logging.info(self._start_msg)

  def Check(self, request: auth_pb2.CheckRequest, context: ServicerContext) -> auth_pb2.CheckResponse:
    """Process the authorization check request.
    
    This method is called by gRPC when a Check request is received.
    It delegates the actual authorization logic to the parent processor.
    
    Args:
        request: The authorization check request.
        context: RPC context of the incoming call.
        
    Returns:
        CheckResponse: The authorization decision.
    """
    return self._processor.Check(request, context)
