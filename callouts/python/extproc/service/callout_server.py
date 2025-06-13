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
Uses multiprocessing for improved concurrency.
"""

from concurrent import futures
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
import logging
import ssl
from typing import Iterator, Union, Iterable, Any

import multiprocessing
import os

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


def run_grpc_worker_entrypoint(
  callout_server_class: type['CalloutServer'],
  worker_init_kwargs: dict[str, Any],
  shutdown_event: multiprocessing.Event
):
  """Entry point for gRPC worker processes.

  Args:
    callout_server_class: The class type of the callout server (typically
      `CalloutServer` or a subclass thereof) that will handle requests
      within this worker process.
    worker_init_kwargs: A dictionary containing keyword arguments needed to
      initialize the `callout_server_class` instance within the worker.
    shutdown_event: A `multiprocessing.Event` object. The main process
      sets this event to signal all worker processes to shut down.
  """
  logging.basicConfig(level=logging.INFO,
                      format='%(asctime)s - %(levelname)s - %(processName)s (%(process)d) - %(message)s')
  processor_instance = callout_server_class(**worker_init_kwargs)
  logging.info("gRPC worker process started with recreated processor instance.")
  grpc_service_instance = _GRPCCalloutService(processor=processor_instance)
  grpc_service_instance.start()
  try:
    shutdown_event.wait()
    logging.info("Shutdown event received in worker, stopping gRPC server.")
  except KeyboardInterrupt:
    logging.info("KeyboardInterrupt in worker process, stopping gRPC server.")
  finally:
    logging.info("Worker process ensuring gRPC server is stopped.")
    grpc_service_instance.stop()
    logging.info("gRPC server in worker process stopped.")


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
    num_processes: The number of gRPC worker processes to spawn by the main instance.
      If None, defaults to the number of CPUs available. Set to 1 to effectively
      disable multiprocessing for gRPC workers.
    is_worker_processor_instance: Internal flag. True if this instance of
      CalloutServer is running within a worker process. This is set internally
      and should not typically be modified by the user.
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
      num_processes: int | None = None,
      is_worker_processor_instance: bool = False
  ):
    self._is_worker_processor_instance = is_worker_processor_instance
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
    self.private_key = private_key if private_key is not None else _read_cert_file(
      private_key_path)
    self.cert_chain = cert_chain if cert_chain is not None else _read_cert_file(
      cert_chain_path)

    if not self._is_worker_processor_instance:
      self._setup = False
      self._shutdown_initiated = False
      self._closed = False
      self._health_check_server: HTTPServer | None = None


      self.num_processes = num_processes if num_processes is not None else os.cpu_count()
      if self.num_processes is None or self.num_processes < 1:
        logging.warning(
          "Could not determine CPU count or invalid num_processes, defaulting to 1 worker.")
        self.num_processes = 1

      self._grpc_shutdown_event = multiprocessing.Event()
      self._grpc_worker_processes: list[multiprocessing.Process] = []



      self.secure_health_check = secure_health_check
      if self.secure_health_check:
        if not (private_key_path or self.private_key) or not (
          cert_chain_path or self.cert_chain):
          logging.error(
            "Secure health check requires private key and certificate chain.")
          self.secure_health_check = False
        else:
          try:
            self.health_check_ssl_context = ssl.SSLContext(
              ssl.PROTOCOL_TLS_SERVER)
            keyfile_for_hc = private_key_path if private_key_path else None
            certfile_for_hc = cert_chain_path if cert_chain_path else None
            if not keyfile_for_hc or not certfile_for_hc:
              logging.error(
                "Secure health check requires private_key_path and cert_chain_path for SSLContext.")
              self.secure_health_check = False
            else:
              self.health_check_ssl_context.load_cert_chain(
                certfile=certfile_for_hc, keyfile=keyfile_for_hc)
          except Exception as e:
            logging.error(
              f"Failed to load SSL context for secure health check: {e}")
            self.secure_health_check = False

      if self.private_key is None or self.cert_chain is None:
        logging.warning(
          "Main Server: Private key or certificate chain is not fully loaded. Secure gRPC server might not start if these are required by workers.")

  def run(self) -> None:
    """Start all requested servers and listen for new connections; blocking."""

    if self._is_worker_processor_instance: logging.error(
      "run() should not be called on a worker."); return
    if self._setup and not self._closed: logging.warning(
      "Server is already running."); return
    if self._closed: logging.error(
      "Server has been shutdown and cannot be restarted."); return

    self._grpc_shutdown_event.clear()
    self._start_servers()
    self._setup = True
    self._closed = False
    logging.info("CalloutServer: All servers/processes initiated.")
    try:
      self._loop_server()
    except KeyboardInterrupt:
      logging.info(
        'CalloutServer: KeyboardInterrupt received, initiating shutdown.')
    finally:
      logging.info('CalloutServer: Initiating shutdown sequence.')
      self.shutdown()
      self._closed = True
      logging.info('CalloutServer: Shutdown complete.')

  def _start_servers(self) -> None:
    """Start the requested servers."""
    if self._is_worker_processor_instance: return

    if self.health_check_address:
      self._health_check_server = HTTPServer(self.health_check_address,
                                             HealthCheckService)
      protocol = 'HTTP'
      if self.secure_health_check and hasattr(self, 'health_check_ssl_context'):
        try:
          self._health_check_server.socket = (
            self.health_check_ssl_context.wrap_socket(
              sock=self._health_check_server.socket, server_side=True))
          protocol = 'HTTPS'
        except Exception as e:
          logging.error(
            f"Failed to wrap health check socket with SSL: {e}. Starting as HTTP.")
      logging.info('%s health check server bound to %s.', protocol,
                   _addr_to_str(self.health_check_address))

    worker_init_kwargs = {
      'address': self.address, 'plaintext_address': self.plaintext_address,
      'disable_plaintext': self.plaintext_address is None,
      'cert_chain': self.cert_chain, 'private_key': self.private_key,
      'cert_chain_path': None, 'private_key_path': None,
      'server_thread_count': self.server_thread_count,
      'is_worker_processor_instance': True,
    }

    logging.info(
      f"Starting {self.num_processes} gRPC worker process(es).")
    for i in range(self.num_processes):
      process_name = f'gRPCWorker-{i + 1}'
      process = multiprocessing.Process(
        target=run_grpc_worker_entrypoint,
        args=(self.__class__, worker_init_kwargs, self._grpc_shutdown_event),
        name=process_name
      )
      self._grpc_worker_processes.append(process)
      process.start()
      logging.info(f"Process {process_name} (PID {process.pid}) started.")

  def _loop_server(self) -> None:
    """Loop server forever, calling shutdown will cause the server to stop."""

    if self._is_worker_processor_instance: return
    if self._health_check_server:
      logging.info("Health check server started.")
      self._health_check_server.serve_forever()
      logging.info("Health check server has stopped serving.")
    else:
      logging.info(
        "Main process waiting for shutdown signal (no health check server).")
      self._grpc_shutdown_event.wait()
      logging.info("Main process received shutdown signal.")

  def shutdown(self) -> None:
    """Tell the server to shutdown, ending all serving threads."""
    if self._is_worker_processor_instance: return
    if self._shutdown_initiated: logging.info(
      "Shutdown already in progress."); return
    self._shutdown_initiated = True
    logging.info("CalloutServer: Starting shutdown...")

    if hasattr(self, '_grpc_shutdown_event'): self._grpc_shutdown_event.set()

    if hasattr(self, '_health_check_server') and self._health_check_server:
      logging.info("Shutting down health check server...")
      self._health_check_server.shutdown()
      self._health_check_server.server_close()
      logging.info('Health check server stopped.')
      self._health_check_server = None

    if hasattr(self, '_grpc_worker_processes'):
      logging.info("Joining gRPC worker processes...")
      for process in self._grpc_worker_processes:
        if process.is_alive():
          logging.info(f"Joining process {process.name} (PID {process.pid})...")
          process.join(timeout=25)
          if process.is_alive():
            logging.warning(
              f"Process {process.name} did not exit gracefully, terminating.")
            process.terminate()
            process.join()
          else:
            logging.info(f"Process {process.name} joined successfully.")
        else:
          logging.info(f"Process {process.name} was already stopped.")
      self._grpc_worker_processes = []
      logging.info("All gRPC worker processes joined/terminated.")

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
        case ProcessingResponse() as processing_response:
          return processing_response
        case ImmediateResponse() as immediate_headers:
          return ProcessingResponse(immediate_response=immediate_headers)
        case HeadersResponse() | None as header_response:
          return ProcessingResponse(request_headers=header_response)
        case _:
          logging.warning("MALFORMED CALLOUT %s", callout)
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
          logging.warning("MALFORMED CALLOUT %s", callout)
    elif callout.HasField('response_body'):
      return ProcessingResponse(
          response_body=self.on_response_body(callout.response_body, context))
    return ProcessingResponse()

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


class _GRPCCalloutService(ExternalProcessorServicer):
  """GRPC based Callout server implementation."""
  def __init__(self, processor: CalloutServer, *args, **kwargs):
    self._processor = processor
    server_options = (('grpc.so_reuseport', 1),)
    self._server = grpc.server(
      futures.ThreadPoolExecutor(max_workers=processor.server_thread_count),
      options=server_options)
    add_ExternalProcessorServicer_to_server(self, self._server)
    self._start_msg = ""
    can_start_secure = False
    if processor.private_key and processor.cert_chain:
      try:
        creds = grpc.ssl_server_credentials(
          [(processor.private_key, processor.cert_chain)])
        addr_str = _addr_to_str(processor.address)
        self._server.add_secure_port(addr_str, creds)
        self._start_msg = f'gRPC callout server (secure) listening on {addr_str}'
        can_start_secure = True
      except Exception as e:
        logging.error(f"Failed to add secure port {processor.address}: {e}")
        self._start_msg = 'gRPC (secure port FAILED)'
    else:
      self._start_msg = 'gRPC (secure port NOT configured)'
      logging.info(self._start_msg)

    can_start_plaintext = False
    if processor.plaintext_address:
      addr_str_plain = _addr_to_str(processor.plaintext_address)
      try:
        self._server.add_insecure_port(addr_str_plain)
        current_status = self._start_msg + " | " if self._start_msg and not (
            'NOT configured' in self._start_msg or 'FAILED' in self._start_msg) else ""
        self._start_msg = f'{current_status}gRPC (plaintext) listening on {addr_str_plain}'
        can_start_plaintext = True
      except Exception as e:
        logging.error(f"Failed to add insecure port {addr_str_plain}: {e}")
        self._start_msg += " | (plaintext port FAILED)"
    if not can_start_secure and not can_start_plaintext: self._start_msg = "gRPC server NOT started: No valid config."

  def stop(self) -> None:
    self._server.stop(grace=10)
    self._server.wait_for_termination(timeout=10)
    logging.info('GRPC server stopped.')

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
