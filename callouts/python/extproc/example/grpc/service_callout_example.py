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

from grpc import ServicerContext
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server


class CalloutServerExample(callout_server.CalloutServer):
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
  def on_request_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Custom processor on request headers."""
    return callout_server.add_header_mutation(
        add=[('header-request', 'request')], remove=['foo'], 
        clear_route_cache=True
    )

  def on_response_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Custom processor on response headers."""
    return callout_server.add_header_mutation(
        add=[('header-response', 'response')]
    )

  def on_request_body(
      self, body: service_pb2.HttpBody, context: ServicerContext
  ) -> service_pb2.BodyResponse:
    """Custom processor on the request body."""
    return callout_server.add_body_mutation(body='-added-body')

  def on_response_body(
      self, body: service_pb2.HttpBody, context: ServicerContext
  ) -> service_pb2.BodyResponse:
    """Custom processor on the response body."""
    return callout_server.add_body_mutation(body='new-body', clear_body=True)


if __name__ == '__main__':
  # Run the gRPC service
  CalloutServerExample(port=443, insecure_port=8080, health_check_port=80).run()
