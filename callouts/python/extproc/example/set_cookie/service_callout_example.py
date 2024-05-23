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
from typing import Union
from grpc import ServicerContext
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server
from extproc.service import callout_tools

def validate_header(request_headers):
  """Validate header for a particular client request."""
  return next((header.raw_value
                   for header in request_headers.headers.headers
                   if header.key == 'cookie-check'), None)

class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  For response header callouts we set a cookie providing a mutation to add 
  a header '{Set-Cookie: cookie}'. This cookie is only set for requests from
  certain clients, based on the presence of the 'cookie-check' header key.
  """

  def on_response_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> Union[service_pb2.HeadersResponse, None]:
    """Custom processor on response headers."""
    if validate_header(headers):
      return callout_tools.add_header_mutation(
        add=[('Set-Cookie', 'your_cookie_name=cookie_value; Max-Age=3600; Path=/')]
      )


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service
  CalloutServerExample().run()
