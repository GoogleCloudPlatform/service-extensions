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

import asyncio
import logging
import ssl
from typing import AsyncIterator, Union

from aiohttp import web
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
import grpc.aio
from grpc import ServicerContext

# Use uvloop for better async performance (Linux/macOS only).
# On Windows, uvloop is not supported and the default asyncio event loop is used.
try:
  import uvloop
  asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
  logging.info("Using uvloop for improved async performance")
except ImportError:
  logging.info("uvloop not available, using default event loop")


def _addr_to_str(address: tuple[str, int]) -> str:
  """Take in an address tuple and returns a formated ip string.

  Args:
      address: Address to transform.

  Returns:
      str: f'{address[0]}:{address[1]}'
  """
  return f'{address[0]}:{address[1]}'


class CalloutServer:
  """Async server wrapper for managing callout servers and processing callouts.

  Attributes:
    secure_address: Address that the main secure (TLS) server will attempt to connect to,
      defaults to default_ip:443. Only used if disable_tls is False.
    health_check_address: The health check serving address,
      defaults to default_ip:80.
    combined_health_check: If True, does not create a separate health check server.
    secure_health_check: If True, will use HTTPS as the protocol of the health check server.
      Requires cert_chain_path and private_key_path to be set.
    plaintext_address: The non-authenticated address to listen to,
      defaults to default_ip:8080.
    disable_plaintext: If true, disables the plaintext address of the server.
    default_ip: If left None, defaults to '0.0.0.0'.
    cert_chain: PEM Certificate chain used to authenticate secure connections,
      required for secure servers.
    cert_chain_path: Relative file path to the cert_chain.
    private_key: PEM private key of the server.
    private_key_path: Relative file path pointing to a file containing private_key data.
    server_thread_count: Kept for compatibility but not used in async server.
    disable_tls: If True, disables the secure (TLS) server. Defaults to True (TLS disabled).
  """

  def __init__(
    self,
    secure_address: tuple[str, int] | None = None,
    health_check_address: tuple[str, int] | None = None,
    combined_health_check: bool = False,
    secure_health_check: bool = False,
    plaintext_address: tuple[str, int] | None = None,
    disable_plaintext: bool = False,
    disable_tls: bool = True,
    default_ip: str | None = None,
    cert_chain: bytes | None = None,
    cert_chain_path: str | None = './extproc/ssl_creds/chain.pem',
    private_key: bytes | None = None,
    private_key_path: str = './extproc/ssl_creds/privatekey.pem',
    server_thread_count: int = 2,
  ):
    self._server: grpc.aio.Server | None = None
    self._health_check_runner: web.AppRunner | None = None
    self._shutdown = False
    default_ip = default_ip or '0.0.0.0'

    self.secure_address: tuple[str, int] = secure_address or (default_ip, 443)

    self.plaintext_address: tuple[str, int] | None = None
    if not disable_plaintext:
      self.plaintext_address = plaintext_address or (default_ip, 8080)

    self.health_check_address: tuple[str, int] | None = None
    if not combined_health_check:
      self.health_check_address = health_check_address or (default_ip, 80)

    self.disable_tls = disable_tls

    if self.disable_tls and self.plaintext_address is None:
      raise ValueError(
        'At least one of secure (TLS) or plaintext listeners must be enabled.')

    def _read_cert_file(path: str | None) -> bytes | None:
      if path:
        try:
          with open(path, 'rb') as file:
            return file.read()
        except FileNotFoundError:
          return None
      return None

    self.server_thread_count = server_thread_count
    self.secure_health_check = secure_health_check
    self.cert_chain_path = cert_chain_path
    self.private_key_path = private_key_path
    # Read cert data.
    self.private_key = private_key or _read_cert_file(private_key_path)
    self.cert_chain = cert_chain or _read_cert_file(cert_chain_path)

    if not self.disable_tls:
      if not self.private_key:
        raise ValueError(
          'TLS is enabled but private key is not provided. '
          'Please provide private_key or private_key_path.')
      if not self.cert_chain:
        raise ValueError(
          'TLS is enabled but certificate chain is not provided. '
          'Please provide cert_chain or cert_chain_path.')

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

  def run(self) -> None:
    """Start all requested servers and listen for new connections; blocking."""
    asyncio.run(self._run_async())

  async def _run_async(self) -> None:
    """Async entry point for running the server."""
    # gRPC tuning for high concurrency
    self._server = grpc.aio.server(
      options=[
        # Allow many concurrent streams for high load
        ('grpc.max_concurrent_streams', 2500),
        # Enable SO_REUSEPORT for better connection distribution
        ('grpc.so_reuseport', 1),
        # Reasonable message size limits
        ('grpc.max_receive_message_length', 4 * 1024 * 1024),
        ('grpc.max_send_message_length', 4 * 1024 * 1024),
        # HTTP2 tuning for high concurrency
        ('grpc.http2.max_pings_without_data', 0),
        ('grpc.http2.min_ping_interval_without_data_ms', 10000),
        ('grpc.http2.min_recv_ping_interval_without_data_ms', 10000),
        # Keepalive settings
        ('grpc.keepalive_time_ms', 30000),
        ('grpc.keepalive_timeout_ms', 60000),
        ('grpc.keepalive_permit_without_calls', 1),
      ]
    )

    # Add servicer
    add_ExternalProcessorServicer_to_server(
      _AsyncGRPCCalloutService(self),
      self._server
    )

    start_msg = 'Async gRPC callout server started'

    # Add secure port if TLS is enabled
    if not self.disable_tls:
      server_credentials = grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(self.private_key, self.cert_chain)]
      )
      self._server.add_secure_port(_addr_to_str(self.secure_address), server_credentials)
      start_msg += f', listening on {_addr_to_str(self.secure_address)} (secure)'

    # Add plaintext port
    if self.plaintext_address:
      self._server.add_insecure_port(_addr_to_str(self.plaintext_address))
      start_msg += f', listening on {_addr_to_str(self.plaintext_address)} (plaintext)'

    await self._server.start()
    logging.info(start_msg)

    # Start health check HTTP server
    if self.health_check_address:
      await self._start_health_check_server()

    try:
      await self._server.wait_for_termination()
    except KeyboardInterrupt:
      logging.info('Server interrupted')
    finally:
      if self._health_check_runner:
        await self._health_check_runner.cleanup()
      await self._server.stop(grace=5)
      logging.info('Server stopped.')

  async def _health_check_handler(self, request: web.Request) -> web.Response:
    """Handle health check HTTP requests."""
    return web.Response(text="OK", status=200)

  async def _start_health_check_server(self) -> None:
    """Start the async HTTP health check server."""
    app = web.Application()
    app.router.add_get('/', self._health_check_handler)
    app.router.add_get('/health', self._health_check_handler)

    self._health_check_runner = web.AppRunner(app)
    await self._health_check_runner.setup()

    ssl_context = None
    protocol = 'HTTP'
    if self.secure_health_check:
      protocol = 'HTTPS'
      ssl_context = self.health_check_ssl_context

    site = web.TCPSite(
      self._health_check_runner,
      self.health_check_address[0],
      self.health_check_address[1],
      ssl_context=ssl_context
    )
    await site.start()
    logging.info('%s health check server listening on %s.', protocol,
                 _addr_to_str(self.health_check_address))

  def shutdown(self) -> None:
    """Tell the server to shutdown, ending all serving threads."""
    self._shutdown = True
    if self._server:
      asyncio.create_task(self._server.stop(grace=5))

  async def process_async(
    self,
    callout: ProcessingRequest,
    context: ServicerContext,
  ) -> ProcessingResponse:
    """Process incoming callouts asynchronously.

    Args:
        callout: The incoming callout.
        context: Stream context on the callout.

    Returns:
        ProcessingResponse: A response for the incoming callout.
    """
    if callout.HasField('request_headers'):
      result = await self.on_request_headers_async(callout.request_headers, context)
      match result:
        case ProcessingResponse() as processing_response:
          return processing_response
        case ImmediateResponse() as immediate_headers:
          return ProcessingResponse(immediate_response=immediate_headers)
        case HeadersResponse() | None as header_response:
          return ProcessingResponse(request_headers=header_response)
        case _:
          logging.warning("MALFORMED CALLOUT %s", callout)
    elif callout.HasField('response_headers'):
      result = await self.on_response_headers_async(callout.response_headers, context)
      return ProcessingResponse(response_headers=result)
    elif callout.HasField('request_body'):
      result = await self.on_request_body_async(callout.request_body, context)
      match result:
        case ImmediateResponse() as immediate_body:
          return ProcessingResponse(immediate_response=immediate_body)
        case BodyResponse() | None as body_response:
          return ProcessingResponse(request_body=body_response)
        case _:
          logging.warning("MALFORMED CALLOUT %s", callout)
    elif callout.HasField('response_body'):
      result = await self.on_response_body_async(callout.response_body, context)
      return ProcessingResponse(response_body=result)
    return ProcessingResponse()

  # Async handler methods - override these in subclasses for async processing
  async def on_request_headers_async(
    self,
    headers: HttpHeaders,
    context: ServicerContext
  ) -> Union[None, HeadersResponse, ImmediateResponse, ProcessingResponse]:
    """Process incoming request headers asynchronously.

    Override this method for custom async header processing.
    Default implementation delegates to sync version.

    Args:
      headers: Request headers to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional header modification object or a complete response.
    """
    return self.on_request_headers(headers, context)

  async def on_response_headers_async(
    self,
    headers: HttpHeaders,
    context: ServicerContext
  ) -> Union[None, HeadersResponse]:
    """Process incoming response headers asynchronously.

    Args:
      headers: Response headers to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional header modification object.
    """
    return self.on_response_headers(headers, context)

  async def on_request_body_async(
    self,
    body: HttpBody,
    context: ServicerContext
  ) -> Union[None, BodyResponse, ImmediateResponse]:
    """Process an incoming request body asynchronously.

    Args:
      body: Request body to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional body modification object.
    """
    return self.on_request_body(body, context)

  async def on_response_body_async(
    self,
    body: HttpBody,
    context: ServicerContext
  ) -> Union[None, BodyResponse]:
    """Process an incoming response body asynchronously.

    Args:
      body: Response body to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional body modification object.
    """
    return self.on_response_body(body, context)

  # Sync handler methods for backward compatibility - override these for simple cases
  def on_request_headers(
    self,
    headers: HttpHeaders,  # pylint: disable=unused-argument
    context: ServicerContext  # pylint: disable=unused-argument
  ) -> Union[None, HeadersResponse, ImmediateResponse, ProcessingResponse]:
    """Process incoming request headers.

    Args:
      headers: Request headers to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional header modification object or a complete response.
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
      body: Request body to process.
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
      body: Response body to process.
      context: RPC context of the incoming callout.

    Returns:
      Optional body modification object.
    """
    return None


class _AsyncGRPCCalloutService(ExternalProcessorServicer):
  """Async gRPC Callout server implementation using grpc.aio."""

  def __init__(self, processor: CalloutServer):
    self._processor = processor

  async def Process(
    self,
    request_iterator: AsyncIterator[ProcessingRequest],
    context: grpc.aio.ServicerContext,
  ) -> AsyncIterator[ProcessingResponse]:
    """Process the client callout asynchronously."""
    async for callout in request_iterator:
      response = await self._processor.process_async(callout, context)
      yield response
