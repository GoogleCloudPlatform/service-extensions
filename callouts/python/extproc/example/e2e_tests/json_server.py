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
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingRequest, ProcessingResponse
from extproc.service import callout_server
from extproc.service import callout_tools
from google.protobuf.wrappers_pb2 import StringValue
from google.protobuf import any_pb2
import json
from google.protobuf.json_format import Parse, ParseDict


d = {
    "first": "a string",
    "second": True,
    "third": 123456789
}

message = ParseDict(d, Thing())
# or
message = Parse(json.dumps(d), Thing())    

print(message.first)  # "a string"
print(message.second) # True
print(message.third)  # 123456789

def unpack_string(value: any_pb2.Any) -> str:
  """Unpacks a string value from a protobuf Any object.

  Args:
    value (google.protobuf.any_pb2.Any): The Any object containing the string value.

  Returns:
    str: The unpacked string value.
  """
  unpacked_value = StringValue()
  value.Unpack(unpacked_value)
  return unpacked_value.value


def check_metadata(request: service_pb2.ProcessingRequest) -> bool:
  """Check if the request contains 'fr' metadata.

  Args:
    request (service_pb2.ProcessingRequest): The processing request to check.

  Returns:
    bool: True if the 'fr' metadata is present and has a non-empty string value, False otherwise.
  """
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


if __name__ == '__main__':
  # Setup command line args.
  args = callout_tools.add_command_line_args().parse_args()
  # Set the debug level.
  logging.basicConfig(level=logging.DEBUG)
  logging.info('Starting json testing server v1.')
  # Run the gRPC service.
  CalloutServer(**vars(args)).run()
