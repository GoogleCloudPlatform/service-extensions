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

import logging
from typing import Any

from grpc import ServicerContext
from http.server import BaseHTTPRequestHandler, HTTPServer
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse, HttpHeaders, BodyResponse
from extproc.service import callout_server
from extproc.service import callout_tools
from extproc.service import command_line_tools
import threading
import json

counters = {
    'request_header_count': 0,
    'request_body_count': 0,
    'response_header_count': 0,
    'response_body_count': 0
}

lock = threading.Lock()


class ObservabilityServerExample(callout_server.CalloutServer):
  """Example observability callout server for use in e2e testing.

    Doesn't perform any mutations to the request or the response.
    Logs callouts to a pollable server interface.
    """

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    # Use the plaintext port for debugging info.
    self.counter_http_server = HTTPServer(('0.0.0.0', 8080), RequestHandler)
    counter_http_server_thread = threading.Thread(
        target=self.counter_http_server.serve_forever)
    counter_http_server_thread.daemon = True
    counter_http_server_thread.start()

  def shutdown(self):
    self.counter_http_server.server_close()
    self.counter_http_server.shutdown()
    return super().shutdown()

  def on_request_headers(self, headers: service_pb2.HttpHeaders,
                         context: ServicerContext) -> HeadersResponse:
    """Custom processor on request headers."""
    logging.info('on_request_headers %s', headers)
    with lock:
      counters['request_header_count'] += 1
    return HeadersResponse()

  def on_request_body(self, body: service_pb2.HttpBody,
                      context: ServicerContext) -> BodyResponse:
    """Custom processor on the request body."""
    logging.info('on_request_body %s', body)
    with lock:
      if (not body.end_of_stream or body.body):
        counters['request_body_count'] += 1
    return BodyResponse()

  def on_response_headers(self, headers: HttpHeaders,
                          context: ServicerContext) -> None | Any:
    logging.info('on_response_headers %s', headers)
    with lock:
      counters['response_header_count'] += 1
    return HeadersResponse()

  def on_response_body(self, body: service_pb2.HttpBody,
                       context: ServicerContext) -> BodyResponse:
    """Custom processor on the response body."""
    logging.info('on_response_body %s', body)
    with lock:
      if (not body.end_of_stream or body.body):
        counters['response_body_count'] += 1
    return BodyResponse()


class RequestHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    if self.path == '/counters':
      self.send_response(200)
      self.send_header('Content-type', 'application/json')
      self.end_headers()
      with lock:
        self.wfile.write(json.dumps(counters).encode())
    else:
      self.send_error(404, "Not Found")


if __name__ == '__main__':
  # Setup command line args.
  args = command_line_tools.add_command_line_args().parse_args()
  # Set the debug level.
  logging.basicConfig(level=logging.DEBUG)
  logging.info('Starting observability test server.')
  # Run the gRPC service.
  params = vars(args)
  # We are using the default plaintext address to provide observability data.
  params['disable_plaintext'] = True
  ObservabilityServerExample(**params).run()
