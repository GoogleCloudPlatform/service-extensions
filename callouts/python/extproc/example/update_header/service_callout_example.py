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

  For request header callouts we provide a mutation to update a header
  '{header-request: request}', and to clear the route cache.

  On response header callouts, we respond with a mutation to update
  the header '{header-response: response}'.
  """
  def on_request_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Custom processor on request headers."""
    return callout_server.add_header_mutation(
        add=[('header-request', 'request-new-value')],
        append_action=2,  #OVERWRITE_IF_EXISTS_OR_ADD
        clear_route_cache=True
    )

  def on_response_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Custom processor on response headers."""
    return callout_server.add_header_mutation(
        add=[('header-response', 'response-new-value')],
        append_action=2  #OVERWRITE_IF_EXISTS_OR_ADD
    )

if __name__ == '__main__':
  # Run the gRPC service
  CalloutServerExample(port=443, insecure_port=8080, health_check_port=80).run()
