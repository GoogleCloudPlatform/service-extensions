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
from grpc import ServicerContext
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import BodyResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpBody
from extproc.service.callout_server import CalloutServer
from extproc.service.callout_tools import add_header_mutation
from extproc.service.callout_tools import add_body_mutation


class BasicCalloutServer(CalloutServer):
  """Example callout server.

  Provides a non-comprehensive set of responses for each of the possible 
  callout interactions.

  For request header callouts we provide a mutation to add a header 
  '{header-request: request}', remove a header 'foo', and to clear the 
  route cache. On response header callouts, we respond with a mutation to add
  the header '{header-response: response}'. On a request body callout we 
  provide a mutation to append '-added-body' to the body. On response body
  callouts we send a mutation to replace the body with 'new-body'.
  """

  def on_request_headers(self, headers: HttpHeaders,
                         context: ServicerContext) -> HeadersResponse:
    """Custom processor on request headers."""
    return add_header_mutation(add=[('header-request', 'request')],
                               remove=['foo'],
                               clear_route_cache=True)

  def on_response_headers(self, headers: HttpHeaders,
                          context: ServicerContext) -> HeadersResponse:
    """Custom processor on response headers."""
    return add_header_mutation(add=[('header-response', 'response')])

  def on_request_body(self, body: HttpBody,
                      context: ServicerContext) -> BodyResponse:
    """Custom processor on the request body."""
    return add_body_mutation(body='-added-body')

  def on_response_body(self, body: HttpBody,
                       context: ServicerContext) -> BodyResponse:
    """Custom processor on the response body."""
    return add_body_mutation(body='new-body', clear_body=True)


if __name__ == '__main__':
  # Run the gRPC service
  logging.basicConfig(level=logging.DEBUG)
  BasicCalloutServer().run()
