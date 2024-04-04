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

import argparse
import logging
from typing import Iterator, Literal
import grpc
from grpc import ServicerContext
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingRequest, ProcessingResponse
from extproc.service import callout_server
from extproc.service import callout_tools
from google.protobuf.wrappers_pb2 import StringValue
from google.protobuf import any_pb2


def unpack_string(value: any_pb2.Any) -> str:
  unpacked_value = StringValue()
  value.Unpack(unpacked_value)
  return unpacked_value.value


def check_metadata(request: service_pb2.ProcessingRequest):
  if not request.HasField('metadata_context'):
    logging.info('No metadata context.')
    return False

  fr_data = None
  for _, feild_data in request.metadata_context.filter_metadata.items():
    if 'fr' in feild_data.fields:
      fr_data = feild_data.fields['fr']
      break

  if fr_data is None:
    logging.info('No "fr" metadata.')
    return False

  logging.info('Contains "fr" key: %s', fr_data)
  return fr_data.HasField('string_value') and fr_data.string_value != ''


default_headers = [('service-callout-response-intercept', 'intercepted'),
                   ('x-used-deltas-gfe3', ''), ('x-used-staging-gfe3', ''),
                   ('x-ext-proc', '')]


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server."""

  def process(self, request_iterator: Iterator[ProcessingRequest],
              context: ServicerContext) -> Iterator[ProcessingResponse]:
    logging.info('Processing request stream.')
    for request in request_iterator:
      logging.info('Received request %s.', request)
      if request.HasField('response_body'):
        yield ProcessingResponse(
            response_body=callout_tools.add_body_mutation('e2e-test'))
        return
      if not check_metadata(request):
        yield ProcessingResponse(
            response_headers=callout_tools.add_header_mutation(
                default_headers),)
      yield ProcessingResponse(
          response_headers=callout_tools.add_header_mutation(
              add=[('metadata', 'found')] + default_headers),)


if __name__ == '__main__':
  # Setup command line args.
  args = callout_tools.add_command_line_args().parse_args()

  # Set the debug level.
  logging.basicConfig(level=logging.DEBUG)
  logging.info('Starting e2e_test server v7.')
  # Run the gRPC service.
  CalloutServerExample(**vars(args)).run()
