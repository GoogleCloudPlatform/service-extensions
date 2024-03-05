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
import os

from concurrent import futures
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from typing import Iterator

import grpc
from grpc import ServicerContext

from extproc.proto import service_pb2
from extproc.proto import service_pb2_grpc

def add_header_mutation(
        add: list[tuple[str, str]] | None = None,
        remove: list[str] | None = None,
        clear_route_cache: bool = False,
) -> service_pb2.HeadersResponse:
    """Generate a header response for incoming requests.

    Args:
      add: A list of tuples representing headers to add.
      remove: List of header strings to remove from the request.
      clear_route_cache: If true, will enable clear_route_cache on the response.

    Returns:
      The constructed header response object.
    """

    header_mutation = service_pb2.HeadersResponse()
    if add:
        header_mutation.response.header_mutation.set_headers.extend([
            service_pb2.HeaderValueOption(
                header=service_pb2.HeaderValue(key=k, raw_value=bytes(v, 'utf-8'))
            )
            for k, v in add
        ])
    if remove is not None:
        header_mutation.response.header_mutation.remove_headers.extend(remove)
    if clear_route_cache:
        header_mutation.response.clear_route_cache = True
    return header_mutation


def update_header_mutation(
        headers: service_pb2.HttpHeaders,
        update: list[tuple[str, str]] | None = None,
        clear_route_cache: bool = False,
) -> service_pb2.HeadersResponse:
    """Generate a header response for incoming requests.

    Args:
      headers: Current headers presented in the request
      update: A list of tuples representing headers to update.
      clear_route_cache: If true, will enable clear_route_cache on the response.

    Returns:
      The constructed header response object.
    """

    header_mutation = service_pb2.HeadersResponse()
    add_dict = {k: bytes(v, 'utf-8') for k, v in update} if update else {}

    for header in headers.headers.headers:
        # Convert existing header value to bytes if it's not already
        existing_value = header.raw_value if isinstance(header.raw_value, bytes) else bytes(header.raw_value, 'utf-8')

        # Use the new value from add_dict if it exists, otherwise use the existing header value
        new_value = add_dict.get(header.key, existing_value)
        header_mutation.response.header_mutation.set_headers.append(
            service_pb2.HeaderValueOption(
                header=service_pb2.HeaderValue(key=header.key, raw_value=new_value),
                append_action=3  # OVERWRITE_IF_EXISTS
            )
        )

    if clear_route_cache:
        header_mutation.response.clear_route_cache = True
    return header_mutation


def normalize_header_mutation(
        headers: service_pb2.HttpHeaders,
        update: list[tuple[str, str]] | None = None,
        clear_route_cache: bool = False,
) -> service_pb2.HeadersResponse:
    """Generate a header response for incoming requests.
    Args:
      headers: Current headers presented in the request
      update: A list of tuples representing headers to update.
      clear_route_cache: If true, will enable clear_route_cache on the response.
    Returns:
      The constructed header response object.
    """
    if update is None:
        update = []

    host_value = next((header.raw_value.decode('utf-8') for header in headers.headers.headers if header.key == 'host'),
                      None)

    if host_value:
        device_type = get_device_type(host_value)
        update.append(('client-device-type', device_type))

    header_mutation = service_pb2.HeadersResponse()
    add_dict = {k: bytes(v, 'utf-8') for k, v in update} if update else {}

    all_headers = list(headers.headers.headers) + [service_pb2.HeaderValue(key=k, raw_value=bytes(v, 'utf-8')) for k, v
                                                   in update]

    for header in all_headers:
        # Use the new value from add_dict if it exists, otherwise use the existing header value
        new_value = add_dict.get(header.key, header.raw_value)
        header_mutation.response.header_mutation.set_headers.append(
            service_pb2.HeaderValueOption(
                header=service_pb2.HeaderValue(key=header.key, raw_value=new_value)
            )
        )

    if clear_route_cache:
        header_mutation.response.clear_route_cache = True
    return header_mutation


def add_body_mutation(
        body: str | None = None,
        clear_body: bool = False,
        clear_route_cache: bool = False,
) -> service_pb2.BodyResponse:
    """Generate a body response for incoming requests.

  Args:
    body: Text of the body.
    clear_body: If set to true, the modification will clear the previous body,
      if left false, the text will be appended to the end of the previous
      body.
    clear_route_cache: If true, will enable clear_route_cache on the response.

  Returns:
    The constructed body response object.
  """

    body_mutation = service_pb2.BodyResponse()
    if body:
        body_mutation.response.body_mutation.body = bytes(body, 'utf-8')
    if clear_body:
        body_mutation.response.body_mutation.clear_body = True
    if clear_route_cache:
        body_mutation.response.clear_route_cache = True
    return body_mutation


def get_device_type(host_value: str) -> str:
    # Simple logic to determine device type based on user agent
    if 'm.example.com' in host_value:
        return 'mobile'
    elif 't.example.com' in host_value:
        return 'tablet'
    else:
        return 'desktop'


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
            cert_path: str = 'localhost.crt',
            cert_key: bytes | None = None,
            cert_key_path: str = 'localhost.key',
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

        # Path to the current file executing
        current_file_path = os.path.abspath(__file__)

        # Path to the extproc
        project_root = os.path.abspath(os.path.join(current_file_path, os.pardir, os.pardir))

        # Read cert data.
        if not cert:
            with open(os.path.join(project_root, 'ssl_creds', cert_path), 'rb') as file:
                self.cert = file.read()
                file.close()
        else:
            self.cert = cert

        if not cert_key:
            with open(os.path.join(project_root, 'ssl_creds', cert_key_path), 'rb') as file:
                self.cert_key = file.read()
                file.close()
        else:
            self.cert_key = cert_key

    def _StartCalloutServer(self) -> grpc.Server:
        """Setup and start a grpc callout server."""
        grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.server_thread_count)
        )
        service_pb2_grpc.add_ExternalProcessorServicer_to_server(
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
        print(start_msg)
        return grpc_server

    def run(self):
        """Start all requested servers and listen for new connections; blocking."""
        self._StartServers()
        self._setup = True
        try:
            self._LoopServer()
        except KeyboardInterrupt:
            print('Server interrupted')
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
            print('Health check server stopped.')

        self._callout_server.stop(grace=10).wait()
        print('GRPC server stopped.')

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
            print(
                'Starting health check server, listening on '
                f'{self.health_check_ip}:{self.health_check_port}'
            )
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
            self, headers: service_pb2.HttpHeaders, context: ServicerContext
    ) -> service_pb2.HeadersResponse:
        """Process incoming request headers.

        Args:
          headers: Request headers to process.
          context: RPC context of the incoming request.

        Returns:
          Header modification object.
        """
        return None

    def on_response_headers(
            self, headers: service_pb2.HttpHeaders, context: ServicerContext
    ) -> service_pb2.HeadersResponse:
        """Process incoming response headers.

        Args:
          headers: Response headers to process.
          context: RPC context of the incoming request.

        Returns:
          Header modification object.
        """
        return None

    def on_request_body(
            self, body: service_pb2.HttpBody, context: ServicerContext
    ) -> service_pb2.BodyResponse:
        """Process an incoming request body.

    Args:
      headers: Request body to process.
      context: RPC context of the incoming request.

    Returns:
      Body modification object.
    """
        return None

    def on_response_body(
            self, body: service_pb2.HttpBody, context: ServicerContext
    ) -> service_pb2.BodyResponse:
        """Process an incoming response body.

    Args:
      headers: Response body to process.
      context: RPC context of the incoming request.

    Returns:
      Body modification object.
    """
        return None
