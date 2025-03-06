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


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  A callout service for request headers targeted to be used with dynamic
  forwarding L7 Load Balancer. Returns ProcessingResponse with dynamic_metadata
  with selected target endpoint.
  """

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.ProcessingResponse:
    """Custom processor on request headers. Returns dynamic forwarding metadate with
    one of the three predefined addresses. Addresses can be selected by the user.
    First two addresses can be selected by a request header. If that is not correct
    or not present 3rd address will be selected.

    Args:
      headers (service_pb2.HttpHeaders): The HTTP headers received in the request.
      context (ServicerContext): The context object for the gRPC service.

    Returns:
      service_pb2.ProcessingResponse: The response containing the dynamic_metadata with
      the selected endpoint.
    """
    known_addresses = ['10.1.10.2', '10.1.10.3']

    ip_to_return = next((header.raw_value.decode('utf-8')
                       for header in headers.headers.headers
                       if header.key == 'ip-to-return'), None)
    if ip_to_return not in known_addresses:
      ip_to_return = '10.1.10.4'

    logging.debug('Selected ip: %s', ip_to_return)
    selected_endpoints = callout_tools.build_dynamic_forwarding_metadata(
      ip_address=ip_to_return,
      port_number=80
    )

    return service_pb2.ProcessingResponse(
      request_headers=service_pb2.HeadersResponse(),
      dynamic_metadata=selected_endpoints
    )


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service
  CalloutServerExample().run()

