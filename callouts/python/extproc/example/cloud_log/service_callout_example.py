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

import google.cloud.logging

from grpc import ServicerContext
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server
from extproc.service import callout_tools


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  For request header callouts we check the content of the request and
  authorize the request or reject the request.
  The content being checked is if the header has the header header-check.
  The decision is logged to Cloud Logging.

  For request body callouts we check the content of the request and
  authorize the request or reject the request.
  The content being checked is if the body has the body body-check.
  The decision is logged to Cloud Logging.
  """

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> service_pb2.HeadersResponse:
    """Custom processor on request headers."""
    return callout_tools.add_header_mutation(
      add=[('header-request', 'request')],
      clear_route_cache=True
    )

  def on_request_body(
      self, body: service_pb2.HttpBody, context: ServicerContext
  ) -> service_pb2.BodyResponse:
    """Custom processor on the request body."""
    return callout_tools.add_body_mutation(body='replaced-body')

if __name__ == '__main__':
  """Sets up Google Cloud Logging for the cloud_log example"""
  client = google.cloud.logging.Client()
  client.setup_logging()

  # Run the gRPC service
  CalloutServerExample(insecure_address=('0.0.0.0', 8080)).run()
