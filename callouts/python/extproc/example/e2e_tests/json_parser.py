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
from typing import Sequence, Mapping
from google.protobuf.json_format import Parse
from google.protobuf.json_format import MessageToJson
from grpc import ServicerContext, StatusCode
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingRequest
from callouts.python.extproc.example.basic_callout_server import (
  BasicCalloutServer,
)
from extproc.service import callout_tools


class MockContext(ServicerContext):
  def is_active(self) -> bool:
    return True

  def time_remaining(self) -> float:
    return -1

  def cancel(self) -> None:
    pass

  def add_callback(self, callback) -> bool:
    return True

  def disable_next_message_compression(self) -> None:
    pass

  def invocation_metadata(self) -> None:
    pass

  def peer(self) -> str:
    return ''

  def peer_identities(self) -> None:
    pass

  def peer_identity_key(self) -> None:
    pass

  def auth_context(self) -> Mapping[str, Sequence[bytes]]:
    return {'': [b'']}

  def set_compression(self, compression) -> None:
    pass

  def send_initial_metadata(self, initial_metadata) -> None:
    pass

  def set_trailing_metadata(self, trailing_metadata) -> None:
    pass

  def trailing_metadata(self) -> None:
    pass

  def abort(self, code, details: str) -> None:
    pass

  def abort_with_status(self, status) -> None:
    pass

  def set_code(self, code) -> None:
    pass

  def code(self) -> StatusCode:
    return StatusCode.OK

  def set_details(self, details: str) -> None:
    pass

  def details(self) -> bytes:
    return b''

  def _finalize_state(self) -> None:
    pass


if __name__ == '__main__':
  # Set the debug level.
  logging.basicConfig(level=logging.DEBUG)
  logging.info('Starting json testing server v1.')
  # Setup command line args.
  parser = callout_tools.add_command_line_args()
  parser.add_argument(
    '--json',
    type=str,
    help=('ProcessingRequest data in json format.'),
  )
  parser.description = (
    'Rather than running a server, this script takes in'
    ' command line json data in the form of a ProcessingRequest and prints'
    ' out the response to the command line.'
  )
  args = parser.parse_args()
  params = vars(args)
  json_data = params.pop('json')
  server = BasicCalloutServer(**params)
  mock_context = MockContext()
  request_data = Parse(json_data, ProcessingRequest())
  response = server.process(request_data, mock_context)
  print(MessageToJson(response))
