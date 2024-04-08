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
from extproc.service import callout_tools


def validation_header_token(request_headers):
  """Determine if the list of invalid token constains the received value."""
  know_bad_tokens = ['badtoken123', 'malicioustoken456', 'compromisedtoken789']
  token = next((header.raw_value for header in request_headers.headers.headers if header.key == 'authorization'), None)

  string_token = token.decode('utf-8') if token else None

  if string_token in know_bad_tokens:
    return False
  return True


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  Provides a non-comprehensive set of responses for each of the possible
  callout interactions.

  For request header callouts we check the content of the request and
  authorize the request or reject the request.
  The content being checked is if the header has a valid token.
  """

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Validate token on request headers."""
    if validation_header_token(headers):
      return callout_tools.add_header_mutation(
        add=[('header-request', 'request')],
        clear_route_cache=True)
    callout_tools.deny_request(context)


if __name__ == '__main__':
  """Sets up Google Cloud Logging for the cloud_log example"""

  # Run the gRPC service
  CalloutServerExample(insecure_address=('0.0.0.0', 8080)).run()
