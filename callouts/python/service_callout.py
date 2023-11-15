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
"""SDK for service callout servers.

Provides a customizeable, out of the box, service callout server.
Takes in service callout requests and performs header and body transformations.
Bundled with an optional health check server.
Can be set up to use ssl certificates.
"""
from concurrent import futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import AnyStr, Iterable, Iterator

import grpc
from grpc import ServicerContext
import service_pb2
import service_pb2_grpc


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
    header_mutation.response.header_mutation.set_headers.extend(
        [
            service_pb2.HeaderValueOption(
                header=service_pb2.HeaderValue(
                    key=k, raw_value=bytes(v, "utf-8")
                )
            )
            for k, v in add
        ]
    )
  if remove is not None:
    header_mutation.response.header_mutation.remove_headers.extend(remove)
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
    clear_body: If set to true, the modififcation will clear the previous body,
      if left false, the text will be appended to the end of the of the previous
      body.
    clear_route_cache: If true, will enable clear_route_cache on the response.

  Returns:
    The constructed body response object.
  """
  body_mutation = service_pb2.BodyResponse()
  if body:
    body_mutation.response.body_mutation.body = bytes(body, "utf-8")
  if clear_body:
    body_mutation.response.body_mutation.clear_body = True
  if clear_route_cache:
    body_mutation.response.clear_route_cache = True
  return body_mutation


class HealthCheckServer(BaseHTTPRequestHandler):
  """Server for responding to health check pings."""

  def do_GET(self) -> None:
    """Returns an empty page with 200 status code."""
    self.send_response(200)
    self.end_headers()


class CalloutServer(service_pb2_grpc.ExternalProcessorServicer):
  """Server for capturing and responding to service callout requests.

  Attributes:
    ip: Address that the main, server will attempt to connect to.
    port: Serving port of the main service.
    insecure_port: If using a grpc server, the port to serve non secure traffic on.
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
  """

  def __init__(
      self,
      ip: str = "0.0.0.0",
      port: int = 8443,
      insecure_port: int = 8080,
      health_check_ip: str = "0.0.0.0",
      health_check_port: int = 8000,
      serperate_health_check: bool = False,
      cert: bytes | None = None,
      cert_path: str = "../ssl_creds/localhost.crt",
      cert_key: bytes | None = None,
      cert_key_path: str = "../ssl_creds/localhost.key",
      root_cert: bytes | None = None,
      root_cert_path: str = "../ssl_creds/root.crt",
      server_thread_count: int = 2,
  ):
    self.ip = ip
    self.port = port
    self.insecure_port = insecure_port
    self.health_check_ip = health_check_ip
    self.health_check_port = health_check_port
    self.server_thread_count = server_thread_count
    self.serperate_health_check = serperate_health_check

    # read cert data
    if not cert:
      with open(cert_path, "rb") as file:
        self.cert = file.read()
        file.close()
    else:
      self.cert = cert

    if not cert_key:
      with open(cert_key_path, "rb") as file:
        self.cert_key = file.read()
        file.close()
    else:
      self.cert_key = cert_key

    if not root_cert:
      with open(root_cert_path, "rb") as file:
        self.root_cert = file.read()
        file.close()
    else:
      self.root_cert = root_cert

  def run(self):
    if not self.serperate_health_check:
      health_server = HTTPServer(
          (self.health_check_ip, self.health_check_port), HealthCheckServer
      )
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=self.server_thread_count)
    )
    service_pb2_grpc.add_ExternalProcessorServicer_to_server(self, server)
    server_credentials = grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(self.cert_key, self.cert)]
    )
    server.add_secure_port("%s:%d" % (self.ip, self.port), server_credentials)
    server.add_insecure_port("%s:%d" % (self.ip, self.insecure_port))
    server.start()
    print(
        "Server started, listening on %s:%d and %s:%d"
        % (self.ip, self.port, self.ip, self.insecure_port)
    )
    try:
      if not self.serperate_health_check:
        health_server.serve_forever()
    except KeyboardInterrupt:
      print("Server interrupted")
    finally:
      server.stop()
      if not serperate_health_check:
        health_server.server_close()

  def Process(
      self,
      request_iterator: Iterator[service_pb2.ProcessingRequest],
      context: ServicerContext,
  ) -> Iterator[service_pb2.ProcessingResponse]:
    """Process the client request."""
    for request in request_iterator:
      if request.HasField("request_headers"):
        yield service_pb2.ProcessingResponse(
            request_headers=self.on_request_headers(request.request_headers, context)
        )
      if request.HasField("response_headers"):
        yield service_pb2.ProcessingResponse(
            response_headers=self.on_response_headers(request.response_headers, context)
        )
      if request.HasField("request_body"):
        yield service_pb2.ProcessingResponse(
            request_body=self.on_request_body(request.request_body, context)
        )
      if request.HasField("response_body"):
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


if __name__ == "__main__":
  # Run the gRPC service
  CalloutServer().run()
