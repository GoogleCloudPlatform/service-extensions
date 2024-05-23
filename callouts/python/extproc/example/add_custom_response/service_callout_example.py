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
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server
from extproc.service import callout_tools


def generate_mock_header_response():
  """Generate mock header response."""
  return callout_tools.add_header_mutation([("Mock-Response", "Mocked-Value")])


def generate_mock_body_response():
  """Generate mock body response."""
  return callout_tools.add_body_mutation("Mocked-Body")


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  On a request header callout we check if it contains a header called '{mock:}', if yes then it will
  generate a mock response, otherwise it will follow the standard flow and add a header
  '{header-request: request}'. On response header callouts, we respond with a mutation to add
  the header '{header-response: response}'.

  On a request body callout we check if it contains in the body 'mock', if yes then it will generate
  a mock response, otherwise it will follow the standard flow and provide a mutation to replace the body
  with 'replaced-body'. On response body callouts we send a mutation to replace the body
  with 'new-body'.

  On header callouts, deny and close the connection when containing the header 'bad-header'.
  On body callouts, deny and close the connection when containing the body substring 'bad-body'.
  """

  def on_request_body(self, body: service_pb2.HttpBody,
                      context: ServicerContext):
    """Custom processor on the request body."""
    if callout_tools.body_contains(body, "bad-body"):
      callout_tools.deny_callout(context)
    if callout_tools.body_contains(body, 'mock'):
      return generate_mock_body_response()
    return callout_tools.add_body_mutation(body='replaced-body')

  def on_response_body(self, body: service_pb2.HttpBody,
                       context: ServicerContext):
    """Custom processor on the response body."""
    if callout_tools.body_contains(body, "bad-body"):
      callout_tools.deny_callout(context)
    if callout_tools.body_contains(body, 'mock'):
      return generate_mock_body_response()
    return callout_tools.add_body_mutation()

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext):
    """Custom processor on request headers."""
    if callout_tools.headers_contain(headers, "bad-header"):
      callout_tools.deny_callout(context)
    if callout_tools.headers_contain(headers, "mock"):
      return generate_mock_header_response()
    return callout_tools.add_header_mutation(add=[('header-request', 'request')
                                                 ],
                                             remove=['foo'],
                                             clear_route_cache=True)

  def on_response_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext):
    """Custom processor on response headers."""
    if callout_tools.headers_contain(headers, "bad-header"):
      callout_tools.deny_callout(context)
    if callout_tools.headers_contain(headers, "mock"):
      return generate_mock_header_response()
    return callout_tools.add_header_mutation(add=[('header-response',
                                                   'response')])


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service
  CalloutServerExample().run()