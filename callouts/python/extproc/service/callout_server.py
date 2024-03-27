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

import logging

from concurrent import futures
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from typing import Iterator

import grpc
from grpc import ServicerContext
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import add_ExternalProcessorServicer_to_server
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc

class HealthCheckService(BaseHTTPRequestHandler):
  """Server for responding to health check pings."""

  def do_GET(self) -> None:
    """Returns an empty page with 200 status code."""
    self.send_response(200)
    self.end_headers()


class GRPCCalloutService(service_pb2_grpc.ExternalProcessorServicer):
  """HTTP based Callout server implementation."""

  def __init__(self, processor, *args, **kwargs):
    self.processor = processor

  def Process(
      self,
      request_iterator: Iterator[service_pb2.ProcessingRequest],
      context: ServicerContext,
  ) -> Iterator[service_pb2.ProcessingResponse]:
    """Process the client request."""
    return self.processor.process(request_iterator, context)


class CalloutServer:
  """Server wrapper for managing callout servers and processing callouts.

  Attributes:
    ip: Address that the main, server will attempt to connect to.
    port: Serving port of the main service.
    insecure_port: If using a grpc server, the port to serve non secure traffic
      on.
    health_check_ip: The health check serving address.
    health_check_port: Serving port of the health check service.
    server_thread_count: Threads allocated to the main grpc service.
    serperate_health_check: If set to false, will not bring up a the health
      check service.
    cert: If speficied, certificate used to authenticate the main grpc service
      for secure htps and http connections. If not specified will attempt to
      load data from a file pointed to by the cert_path.
    cert_path: Relative file path pointing to the main grpc certificate, cert.
    cert_key: Public key of the grpc certificate.
    cert_key_path: Relative file path pointing to the cert_key.
    root_cert: Root certificate for the main grpc service.
    root_cert_path: Relative file path pointing to the root_cert.
    use_grpc: Use grpc for the main callout service.
    enable_insecure_port: Also listen for connections without certificates on
      the insecure port.
  """

  def __init__(
      self,
      ip: str = '0.0.0.0',
      port: int = 8443,
      insecure_port: int = 8080,
      health_check_ip: str = '0.0.0.0',
      health_check_port: int = 8000,
      serperate_health_check: bool = False,
      cert: bytes | None = None,
      cert_path: str = './extproc/ssl_creds/localhost.crt',
      cert_key: bytes | None = None,
      cert_key_path: str = './extproc/ssl_creds/localhost.key',
      server_thread_count: int = 2,
      enable_insecure_port: bool = True,
  ):
    self._setup = False
    self._shutdown = False
    self._closed = False

    self.ip = ip
    self.port = port
    self.insecure_port = insecure_port
    self.health_check_ip = health_check_ip
    self.health_check_port = health_check_port
    self.server_thread_count = server_thread_count
    self.serperate_health_check = serperate_health_check
    self.enable_insecure_port = enable_insecure_port
    # Read cert data.
    if not cert:
      with open(cert_path, 'rb') as file:
        self.cert = file.read()
        file.close()
    else:
      self.cert = cert

    if not cert_key:
      with open(cert_key_path, 'rb') as file:
        self.cert_key = file.read()
        file.close()
    else:
      self.cert_key = cert_key

  def _StartCalloutServer(self) -> grpc.Server:
    """Setup and start a grpc callout server."""
    grpc_server = grpc.server(
      futures.ThreadPoolExecutor(max_workers=self.server_thread_count)
    )
    add_ExternalProcessorServicer_to_server(
        GRPCCalloutService(self), grpc_server
    )
    server_credentials = grpc.ssl_server_credentials(
      private_key_certificate_chain_pairs=[(self.cert_key, self.cert)]
    )
    grpc_server.add_secure_port(f'{self.ip}:{self.port}', server_credentials)
    start_msg = (
      f'GRPC callout server started, listening on {self.ip}:{self.port}'
    )
    if self.enable_insecure_port:
      grpc_server.add_insecure_port(f'{self.ip}:{self.insecure_port}')
      start_msg += f' and {self.ip}:{self.insecure_port}'
    grpc_server.start()
    logging.info(start_msg)
    return grpc_server

  def run(self):
    """Start all requested servers and listen for new connections; blocking."""
    self._StartServers()
    self._setup = True
    try:
      self._LoopServer()
    except KeyboardInterrupt:
      logging.info('Server interrupted')
    finally:
      self._StopServers()
      self._closed = True

  def _StartServers(self):
    """Start the requested servers."""
    if not self.serperate_health_check:
      self._health_check_server = HTTPServer(
        (self.health_check_ip, self.health_check_port), HealthCheckService
      )
    self._callout_server = self._StartCalloutServer()

  def _StopServers(self):
    """Close the sockets of all servers, and trigger shutdowns."""
    if not self.serperate_health_check:
      self._health_check_server.server_close()
      self._health_check_server.shutdown()
      logging.info('Health check server stopped.')

    self._callout_server.stop(grace=10).wait()
    logging.info('GRPC server stopped.')

  def _LoopServer(self):
    """Loop server forever, calling shutdown will cause the server to stop."""

    # We chose the main serving thread based on what server configuration
    # was requested. Defaults to the health check thread.
    if self.serperate_health_check:
      # If the only server requested is a grpc callout server, we loop
      # this main thread while the server is running.
      while not self._shutdown:
        pass
    else:
      logging.info('Starting health check server, listening on %s:%s',
                   self.health_check_ip, self.health_check_port)
      self._health_check_server.serve_forever()

  def shutdown(self):
    """Tell the server to shutdown, ending all serving threads."""
    if not self.serperate_health_check:
      self._health_check_server.shutdown()
    self._shutdown = True

  def process(
      self,
      request_iterator: Iterator[service_pb2.ProcessingRequest],
      context: ServicerContext,
  ) -> Iterator[service_pb2.ProcessingResponse]:
    """Process the client request."""
    for request in request_iterator:
      if request.HasField('request_headers'):
        yield service_pb2.ProcessingResponse(
            request_headers=self.on_request_headers(
                request.request_headers, context
            )
        )
      if request.HasField('response_headers'):
        yield service_pb2.ProcessingResponse(
            response_headers=self.on_response_headers(
                request.response_headers, context
            )
        )
      if request.HasField('request_body'):
        yield service_pb2.ProcessingResponse(
            request_body=self.on_request_body(request.request_body, context)
        )
      if request.HasField('response_body'):
        yield service_pb2.ProcessingResponse(
            response_body=self.on_response_body(request.response_body, context)
        )

  def on_request_headers(
      self,
      headers: service_pb2.HttpHeaders,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | service_pb2.HeadersResponse:
    """Process incoming request headers.

    Args:
      headers: Request headers to process.
      context: RPC context of the incoming request.

    Returns:
      Header modification object.
    """
    return None

  def on_response_headers(
      self,
      headers: service_pb2.HttpHeaders,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | service_pb2.HeadersResponse:
    """Process incoming response headers.

    Args:
      headers: Response headers to process.
      context: RPC context of the incoming request.

    Returns:
      Header modification object.
    """
    return None

  def on_request_body(
      self,
      body: service_pb2.HttpBody,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | service_pb2.BodyResponse:
    """Process an incoming request body.

Args:
  headers: Request body to process.
  context: RPC context of the incoming request.

Returns:
  Body modification object.
"""
    return None

  def on_response_body(
      self,
      body: service_pb2.HttpBody,  # pylint: disable=unused-argument
      context: ServicerContext  # pylint: disable=unused-argument
  ) -> None | service_pb2.BodyResponse:
    """Process an incoming response body.

Args:
  headers: Response body to process.
  context: RPC context of the incoming request.

Returns:
  Body modification object.
"""
    return None
