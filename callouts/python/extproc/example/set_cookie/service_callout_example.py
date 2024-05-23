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

from typing import Union
from grpc import ServicerContext
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server
from extproc.service import callout_tools

def validate_header(http_headers: service_pb2.HttpHeaders) -> Union[str, None]:
  """Validate if the incomming headers contain the 'cookie-check' header.

  This function checks if the 'cookie-check' header is present in the
  headers and returns its raw value if found.

  Args:
      http_headers (service_pb2.HttpHeaders): Incomming http headers to check.

  Returns:
      str or None: The raw value of the 'cookie-check' header if found, otherwise None.
  """
  return next((header.raw_value
                   for header in http_headers.headers.headers
                   if header.key == 'cookie-check'), None)

class CalloutServerExample(callout_server.CalloutServer):
  """Example Set Cookie / Callout server.

  For response header callouts we set a cookie providing a mutation to add 
  a header '{Set-Cookie: cookie}'. This cookie is only set for requests from
  certain clients, based on the presence of the 'cookie-check' header key.

  Usage:
    To use this example callout server, instantiate the CalloutServerExample
    class and run the gRPC service.
  """

  def on_response_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Custom processor on response headers.

    This method should set cookie on http response for a particular client request.

    Args:
      headers (service_pb2.HttpHeaders): The HTTP headers received in the response.
      context (ServicerContext): The context object for the gRPC service.

    Returns:
      service_pb2.HeadersResponse: The response containing the mutations to be applied
      to the response headers.
    """
    if validate_header(headers):
      return callout_tools.add_header_mutation(
        add=[('Set-Cookie', 'your_cookie_name=cookie_value; Max-Age=3600; Path=/')]
      )


if __name__ == '__main__':
  # Run the gRPC service
  CalloutServerExample().run()
