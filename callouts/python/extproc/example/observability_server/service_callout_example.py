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
from typing import Any

from grpc import ServicerContext
from http.server import BaseHTTPRequestHandler, HTTPServer
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse, HttpHeaders, BodyResponse
from extproc.service import callout_server
import threading
import json

counters = {
  'request_header_count': 0,
  'request_body_count': 0,
  'response_header_count': 0,
  'response_body_count': 0
}

class AsyncServerExample(callout_server.CalloutServer):
    """Example async server.

    Doesn't perform any mutations to the request or the response.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lock = threading.Lock()

    def on_request_body(self, body: service_pb2.HttpBody, context: ServicerContext) -> BodyResponse:
        """Custom processor on the request body."""
        with self.lock:
            counters['request_header_count'] += 1
        return BodyResponse()

    def on_request_headers(self, headers: service_pb2.HttpHeaders, context: ServicerContext) -> HeadersResponse:
        """Custom processor on request headers."""
        with self.lock:
            counters['request_header_count'] += 1
        return HeadersResponse()

    def on_response_headers(self, headers: HttpHeaders, context: ServicerContext) -> None | Any:
        with self.lock:
            counters['response_header_count'] += 1
        return HeadersResponse()

    def on_response_body(self, body: service_pb2.HttpBody, context: ServicerContext) -> BodyResponse:
        """Custom processor on the response body."""
        with self.lock:
            counters['response_body_count'] += 1
        return BodyResponse()

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/counters':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(counters).encode())
        else:
            self.send_error(404, "Not Found")

if __name__ == '__main__':
  counter_http_server = HTTPServer(('0.0.0.0', 10000), RequestHandler)
  counter_http_server = threading.Thread(target=counter_http_server.serve_forever)
  counter_http_server.daemon = True
  counter_http_server.start()
  AsyncServerExample(insecure_address=('0.0.0.0', 8080)).run()
  
