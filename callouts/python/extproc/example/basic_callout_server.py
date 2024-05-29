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
from extproc.service.callout_tools import add_command_line_args


class BasicCalloutServer(CalloutServer):
  """Example callout server.

  A non-comprehensive set of examples for each of the possible callout actions.
  """

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

  def on_request_headers(self, headers: HttpHeaders, _) -> HeadersResponse:
    """Custom processor on request headers.
    
    This example contains a few of the possible modifications that can be
    applied to a request header callout:
    
    * A change to the ':host' and ':path' headers.
    * Adding the header 'header-request' with the value of 'request'.
    * Removal of a header 'foo'.
    * Clearing of the route cache.
    
    """
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
    """Custom processor on response headers.
    
    Generates an addition to the response headers containing:
    'hello: service-extensions'.
    """
    logging.debug("Received response headers callout: %s", headers)
    return add_header_mutation(add=[('hello', 'service-extensions')])

  def on_request_body(self, body: HttpBody, _) -> BodyResponse:
    """Custom processor on the request body.

    Generates a request body modification replacing the request body with
    'replaced-body'.
    """
    logging.debug("Received request body callout: %s", body)
    return add_body_mutation(body='replaced-body')

  def on_response_body(self, body: HttpBody, _) -> BodyResponse:
    """Custom processor on the response body.
    
    Generates a response body modification clearing the response body.
    """
    logging.debug("Received response body callout: %s", body)
    return add_body_mutation(clear_body=True)


if __name__ == '__main__':
  # Useful command line args.
  args = add_command_line_args().parse_args()
  # Set the logging debug level.
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service.
  BasicCalloutServer(**vars(args)).run()
