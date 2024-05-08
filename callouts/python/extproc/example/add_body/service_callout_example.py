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

from grpc import ServicerContext
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  Provides a non-comprehensive set of responses for each of the possible
  callout interactions.

  For request body callouts, we offer a mutation to append '-added-body'
  to the existing body content. In response body callouts, our solution
  involves sending a mutation to replace the current body with 'new-body'.
  """

  def on_request_body(
      self, body: service_pb2.HttpBody, context: ServicerContext
  ) -> service_pb2.BodyResponse:
    """Custom processor on the request body.

    Args:
      body (service_pb2.BodyResponse): The HTTP body received in the request.
      context (ServicerContext): The context object for the gRPC service.

    Returns:
      service_pb2.BodyResponse: The response containing the mutations to be applied
      to the request body.
    """
    return callout_server.add_body_mutation(body='-added-body')

  def on_response_body(
      self, body: service_pb2.HttpBody, context: ServicerContext
  ) -> service_pb2.BodyResponse:
    """Custom processor on the response body.

        Args:
          body (service_pb2.BodyResponse): The HTTP body received in the response.
          context (ServicerContext): The context object for the gRPC service.

        Returns:
          service_pb2.BodyResponse: The response containing the mutations to be applied
          to the response body.
        """
    return callout_server.add_body_mutation(body='new-body', clear_body=True)


if __name__ == '__main__':
  # Run the gRPC service
  CalloutServerExample(address=('0.0.0.0', 443),
                       insecure_address=('0.0.0.0', 8080),
                       health_check_address=('0.0.0.0', 80)).run()
