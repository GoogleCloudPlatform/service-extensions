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
from envoy.config.core.v3.base_pb2 import HeaderValue
from envoy.config.core.v3.base_pb2 import HeaderValueOption
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server
from extproc.service import callout_tools


def validate_request_header(request_headers):
  """Validate header of the request."""
  return not next((header.raw_value
                   for header in request_headers.headers.headers
                   if header.key == 'header-check'), None)


def validate_body(body):
  """Validate body of the request."""
  return "body-check" not in body.body.decode('utf-8')


def generate_mock_header_response():
  """Generate mock header response."""
  mock_response = service_pb2.HeadersResponse()
  mock_header = HeaderValueOption(header=HeaderValue(
      key="Mock-Response", raw_value=bytes("Mocked-Value", 'utf-8')))
  mock_response.response.header_mutation.set_headers.append(mock_header)
  return mock_response


def generate_mock_body_response():
  """Generate mock body response."""
  mock_response = service_pb2.BodyResponse()
  mock_response.response.body_mutation.body = bytes("Mocked-Body", 'utf-8')
  return mock_response


def header_mock_check(http_headers: service_pb2.HttpHeaders):
  """Check for the "mock" header in the request"""
  return not next((header.raw_value
                   for header in http_headers.headers.headers
                   if header.key == 'mock'), None)


def body_mock_check(http_body: service_pb2.HttpBody):
  """Check for the "mock" string in the request body"""
  return "mock" in http_body.body.decode('utf-8')


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  Provides a non-comprehensive set of responses for each of the possible
  callout interactions.

  On a request header callout we check if it contains a header called '{mock:}', if yes then it will
  generate a mock response, otherwise it will follow the standard flow and add a header
  '{header-request: request}'. On response header callouts, we respond with a mutation to add
  the header '{header-response: response}'.

  On a request body callout we check if it contains in the body 'mock', if yes then it will generate
  a mock response, otherwise it will follow the standard flow and provide a mutation to append '-added-body'
  to the body. On response body callouts we send a mutation to replace the body with 'new-body'.
  """

  def on_request_body(self, body: service_pb2.HttpBody,
                      context: ServicerContext):
    """Custom processor on the request body."""
    if validate_body(body):
      callout_tools.deny_request(context)
    if body_mock_check(body):
      return generate_mock_body_response()
    return callout_tools.add_body_mutation(body='-added-body')

  def on_response_body(self, body: service_pb2.HttpBody,
                       context: ServicerContext):
    """Custom processor on the response body."""
    if validate_body(body):
      callout_tools.deny_request(context)
    if body_mock_check(body):
      return generate_mock_body_response()
    return callout_tools.add_body_mutation(body='new-body', clear_body=False)

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext):
    """Custom processor on request headers."""
    if validate_request_header(headers):
      callout_tools.deny_request(context)
    if header_mock_check(headers):
      return generate_mock_header_response()
    return callout_tools.add_header_mutation(add=[('header-request', 'request')
                                                 ],
                                             remove=['foo'],
                                             clear_route_cache=True)

  def on_response_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext):
    """Custom processor on response headers."""
    if validate_request_header(headers):
      callout_tools.deny_request(context)
    if header_mock_check(headers):
      return generate_mock_header_response()
    return callout_tools.add_header_mutation(add=[('header-response',
                                                   'response')])


if __name__ == '__main__':
  # Run the gRPC service
  CalloutServerExample(insecure_address=('0.0.0.0', 8080)).run()