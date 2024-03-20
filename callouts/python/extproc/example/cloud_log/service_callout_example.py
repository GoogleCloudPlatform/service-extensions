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
from extproc.proto import service_pb2
from extproc.service import callout_server


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  Provides a non-comprehensive set of responses for each of the possible
  callout interactions.

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
    return callout_server.add_header_mutation(
      add=[('header-request', 'request')],
      clear_route_cache=True
    )

  def on_request_body(
      self, body: service_pb2.HttpBody, context: ServicerContext
  ) -> service_pb2.BodyResponse:
    """Custom processor on the request body."""
    return callout_server.add_body_mutation(body='-added-body')

if __name__ == '__main__':
  """Sets up Google Cloud Logging for the cloud_log example"""
  client = google.cloud.logging.Client()
  client.setup_logging()

  # Run the gRPC service
  CalloutServerExample(port=443, insecure_port=8080, health_check_port=80).run()
