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

  On a request header callout we perform a redirect to 
  '{http://service-extensions.com/redirect}' with the status of
  '{301}' - MovedPermanently returning an ImmediateResponse.
  """

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext) -> service_pb2.ImmediateResponse:
    """Custom processor on request headers."""
    return callout_tools.header_immediate_response(
        code=301,
        headers=[('Location', 'http://service-extensions.com/redirect')])


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service
  CalloutServerExample().run()