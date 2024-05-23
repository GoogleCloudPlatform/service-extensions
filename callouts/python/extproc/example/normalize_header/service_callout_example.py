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
from extproc.service import callout_tools
from extproc.service import callout_server


def get_device_type(host_value: str) -> str:
  """Determine device type based on user agent."""

  if 'm.example.com' in host_value:
    return 'mobile'
  elif 't.example.com' in host_value:
    return 'tablet'
  return 'desktop'


class CalloutServerExample(callout_server.CalloutServer):
  """Example header normalization callout server.

  For request header callouts we check the host header
  and create a new HTTP header (client-device-type)
  to shard requests based on device.
  """

  def add_device_type_header(
      self, headers: service_pb2.HttpHeaders) -> service_pb2.HeadersResponse:
    """Generate a client-device-type header response.

    Args:
      headers: Current headers presented in the callout.
    Returns:
      The constructed HeadersResponse object.
    """

    host_value = next((header.raw_value.decode('utf-8')
                       for header in headers.headers.headers
                       if header.key == ':host'), None)

    header_mutation = service_pb2.HeadersResponse()

    if host_value:
      device_type = get_device_type(host_value)
      header_mutation = callout_tools.add_header_mutation(
          add=[('client-device-type', device_type)], clear_route_cache=True)

    return header_mutation

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext) -> service_pb2.HeadersResponse:
    """Custom processor on request headers.

    Args:
      headers (service_pb2.HttpHeaders): The HTTP headers received in the request.
      context (ServicerContext): The context object for the gRPC service.

    Returns:
      service_pb2.HeadersResponse: The response containing the mutations to be applied
      to the request headers.
    """
    return self.add_device_type_header(headers=headers)


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service
  CalloutServerExample().run()
