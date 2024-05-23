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

  On a request body callout we provide a mutation to append '-added-body' to
  the body. On response body callouts we send a mutation to replace the body
  with 'new-body'.
  """

  def on_request_body(self, body: service_pb2.HttpBody,
                      context: ServicerContext) -> service_pb2.BodyResponse:
    """Custom processor on the request body."""
    return callout_tools.add_body_mutation(
        body.body.decode('utf-8') + '-added-request-body')

  def on_response_body(self, body: service_pb2.HttpBody,
                       context: ServicerContext) -> service_pb2.BodyResponse:
    """Custom processor on the response body."""
    return callout_tools.add_body_mutation('new-body')


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service
  CalloutServerExample().run()
