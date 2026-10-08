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
"""SDK for network service callout servers.

Provides a customizable network service callout server for L4 processing.
Extends the base callout server functionality for network-level data.
"""

from concurrent import futures
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
import logging
import ssl
from typing import Iterator, Tuple
from typing import Iterable

from envoy.service.network_ext_proc.v3.network_external_processor_pb2 import ProcessingRequest
from envoy.service.network_ext_proc.v3.network_external_processor_pb2 import ProcessingResponse
from envoy.service.network_ext_proc.v3.network_external_processor_pb2_grpc import (
    add_NetworkExternalProcessorServicer_to_server,
    NetworkExternalProcessorServicer,
)

import grpc
from google.protobuf.struct_pb2 import Struct
from grpc import ServicerContext

@dataclass
class ProcessingResult:
  """Holds the result of data processing from a callout handler.

  Attributes:
    processed_data: The data after processing, which may be modified.
    modified: A boolean indicating if the data was changed.
  """
  processed_data: bytes
  modified: bool


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


class NetworkCalloutServer:
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
    """Process incoming network callouts.

    Args:
        callout: The incoming network callout.
        context: Stream context on the callout.

    Returns:
        ProcessingResponse: A response for the incoming callout.
    """
    response = ProcessingResponse()

    # Handle read data (client->server)
    if callout.HasField('read_data'):
      data = callout.read_data.data
      end_of_stream = callout.read_data.end_of_stream

      # Process the data through callback
      processed_data, modified = self.on_read_data(data, end_of_stream, context)
      
      # Build response
      response.read_data.data = processed_data
      response.read_data.end_of_stream = end_of_stream
      response.data_processing_status = (
          ProcessingResponse.MODIFIED if modified
          else ProcessingResponse.UNMODIFIED
      )

      # Check connection control
      conn_status = self.should_close_connection(data, modified, context)

    # Handle write data (server->client)
    elif callout.HasField('write_data'):
      data = callout.write_data.data
      end_of_stream = callout.write_data.end_of_stream

      # Process the data through callback
      processed_data, modified = self.on_write_data(data, end_of_stream, context)

      # Build response
      response.write_data.data = processed_data
      response.write_data.end_of_stream = end_of_stream
      response.data_processing_status = (
          ProcessingResponse.MODIFIED if modified
          else ProcessingResponse.UNMODIFIED
      )

      # Check connection control
      conn_status = self.should_close_connection(data, modified, context)

    else:
      logging.warning("Received request with no data")
      return response

    # Set connection status
    response.connection_status = (
        ProcessingResponse.CLOSE if conn_status
        else ProcessingResponse.CONTINUE
    )

    return response

  def on_read_data(
      self,
      data: bytes,
      end_of_stream: bool,
      context: ServicerContext,
  ) -> ProcessingResult:
    """Process data from client to server (read path).
    
    Override this method to implement custom processing logic.
    
    Args:
        data: Raw bytes from the client
        end_of_stream: Whether this is the last data frame
        context: gRPC context
        
    Returns:
        A ProcessingResult containing the processed data and modification status.
    """
    # Default: pass through unchanged
    return ProcessingResult(processed_data=data, modified=False)

  def on_write_data(
      self,
      data: bytes,
      end_of_stream: bool,
      context: ServicerContext,
  ) -> ProcessingResult:
    """Process data from server to client (write path).
    
    Override this method to implement custom processing logic.
    
    Args:
        data: Raw bytes from the server
        end_of_stream: Whether this is the last data frame
        context: gRPC context
        
    Returns:
        A ProcessingResult containing the processed data and modification status.
    """
    # Default: pass through unchanged
    return ProcessingResult(processed_data=data, modified=False)

  def should_close_connection(
      self,
      data: bytes,
      modified: bool,
      context: ServicerContext
  ) -> bool:
    return False


class _GRPCCalloutService(NetworkExternalProcessorServicer):
  """GRPC based Callout server implementation."""

  def __init__(self, processor, *args, **kwargs):
    self._processor = processor
    self._server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=processor.server_thread_count))
    add_NetworkExternalProcessorServicer_to_server(self, self._server)
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
