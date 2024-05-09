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
import argparse

from envoy.service.ext_proc.v3.external_processor_pb2 import HttpBody
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from envoy.service.ext_proc.v3.external_processor_pb2 import BodyResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
from extproc.service.callout_server import CalloutServer
from extproc.service.callout_tools import add_header_mutation
from extproc.service.callout_tools import add_body_mutation


class BasicCalloutServer(CalloutServer):
  """Example callout server.

  Provides a non-comprehensive set of responses for each of the callout events.
  """

  def on_request_headers(self, headers: HttpHeaders, _) -> HeadersResponse:
    """Custom processor on request headers."""
    logging.debug("Received request headers callout: %s", headers)
    return add_header_mutation(
        add=[
            # Change the host to 'service-extensions.com'.
            (':host', 'service-extensions.com'),
            # Change the destination path to '/'.
            (':path', '/'),
            ('header-request', 'request')
        ],
        remove=['foo'],
        clear_route_cache=True)

  def on_response_headers(self, headers: HttpHeaders, _) -> HeadersResponse:
    """Custom processor on response headers."""
    logging.debug("Received response headers callout: %s", headers)
    return add_header_mutation(add=[('hello', 'service-extensions')])

  def on_request_body(self, body: HttpBody, _) -> BodyResponse:
    """Custom processor on the request body."""
    logging.debug("Received request body callout: %s", body)
    return add_body_mutation(body='-added-body')

  def on_response_body(self, body: HttpBody, _) -> BodyResponse:
    """Custom processor on the response body."""
    logging.debug("Received response body callout: %s", body)
    return add_body_mutation(clear_body=True)


if __name__ == '__main__':
  # Useful command line args.
  parser = argparse.ArgumentParser()
  parser.add_argument('--secure_health_check',
                      action="store_true",
                      help="Run a HTTPS health check rather than an HTTP one.")
  args = parser.parse_args()
  # Set the debug level.
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service.
  BasicCalloutServer(secure_health_check=args.secure_health_check).run()
