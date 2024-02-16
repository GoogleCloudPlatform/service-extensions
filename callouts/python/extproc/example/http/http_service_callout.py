from concurrent import futures
from functools import partial
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from http.server import ThreadingHTTPServer
import threading
from typing import Iterator

import grpc
from grpc import ServicerContext
from grpc._server import _Server
import service_pb2
import service_pb2_grpc


class HTTPCalloutService(BaseHTTPRequestHandler):
  """HTTP based Callout server implementation.

  Untested example.
  """

  def __init__(self, processor, *args, **kwargs):
    self.processor = processor
    super(BaseHTTPRequestHandler, self).__init__(*args, **kwargs)

  def do_GET(self) -> None:
    self.send_response(501)  # Unimplemented.
    self.end_headers()

  def do_POST(self) -> None:
    """Returns an empty page with 200 status code."""
    if 'content-length' in self.headers:
      content = self.rfile.read(int(self.headers.get('content-length')))
      response = self.processor.Process(
          service_pb2.ProcessingRequest.FromString(content), None
      )
    self.send_response(200)
    self.end_headers()

### TODO create a callout server wrapper so that I can supply the callout server version externally.


if self.use_grpc:
      self._grpc_server = self._StartGRPCCalloutServer()
    else:
      if self.serperate_health_check:
        self._http_server = HTTPServer(
            (self.ip, self.port), partial(HTTPCalloutService, self)
        )
      else:
        self._http_server = self._StartHTTPCalloutServer()

def _StopServers(self):
    """Close the sockets of all servers, and trigger shutdowns."""
    if not self.serperate_health_check:
      self._health_check_server.server_close()
      self._health_check_server.shutdown()
      print('Health check server stopped.')
    if self.use_grpc:
      self._grpc_server.stop(grace=10).wait()
      print('GRPC server stopped.')
    else:
      self._http_server.server_close()
      self._http_server.shutdown()
      print('HTTP server stopped.')

  def _LoopServer(self):
    """Loop server forever, calling shutdown will cause the server to stop."""

    # We chose the main serving thread based on what server configuration
    # was requested. Defaults to the health check thread. But will use
    # the callout server thread if the it is a HTTP server and no health
    # check server is present.
    if self.serperate_health_check:
      if self.use_grpc:
        # If the only server requested is a grpc callout server, we loop
        # this main thread while the server is running.
        while not self._shutdown:
          pass
      else:
        print(
            'Starting HTTP callout server, listening on '
            f'{self.ip}:{self.port}'
        )
        self._http_server.serve_forever()


def shutdown(self):
    """Tell the server to shutdown, ending all serving threads."""
    if self.serperate_health_check:
      if not self.use_grpc:
        self._http_server.shutdown()
    else:
      self._health_check_server.shutdown()
    self._shutdown = True


  def _StartHTTPCalloutServer(self) -> ThreadingHTTPServer:
    """Setup and start a http callout server."""
    http_server = ThreadingHTTPServer(
        (self.ip, self.port), partial(HTTPCalloutService, self)
    )
    server_thread = threading.Thread(target=http_server.serve_forever)
    server_thread.deamon = True
    server_thread.start()
    print(f'HTTP callout server started, listening on {self.ip}:{self.port}')
    return http_server