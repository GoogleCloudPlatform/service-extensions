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
from typing import Iterator
import grpc
from google.protobuf.json_format import Parse
from envoy.service.ext_proc.v3.external_processor_pb2 import (
  ProcessingRequest,
  ProcessingResponse,
)
from extproc.tests.basic_grpc_test import _addr_to_str
from extproc.service.callout_tools import _addr
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import (
  ExternalProcessorStub,
)


def make_json_request(
  json_list: list[str], address: tuple[str, int]
) -> Iterator[ProcessingResponse]:
  """Make requests to a callout service with ProcessingRequest json data.
  Args:
    json_list: A list of json strings representing ProcessingRequest data.
    address: ip address of the callout server.
  Returns:
    An iterator containg each response.
  """
  callouts = [Parse(data, ProcessingRequest()) for data in json_list]
  with grpc.insecure_channel(_addr_to_str(address)) as channel:
    stub = ExternalProcessorStub(channel)
    for response in stub.Process(iter(callouts)):
      yield response
  return None


if __name__ == '__main__':
  # Set the debug level.
  logging.basicConfig(level=logging.DEBUG)
  logging.info('Starting json testing server v1.')
  # Setup command line args.
  parser = argparse.ArgumentParser()
  parser.add_argument(
    'address',
    type=_addr,
    help=('Address of the callout server in the format ip:port.'),
  )
  parser.add_argument(
    '-d',
    '--data',
    type=str,
    help=(
      'ProcessingRequest data in json format. Also accepts a list of json'
      ' objects to preform multiple callouts.'
    ),
    nargs='*',
  )
  parser.description = (
    'Sends ProcessingRequest data to a callout server and'
    'prints out the responses.'
  )
  args = parser.parse_args()
  # Preform callouts and print the responses.
  logging.info(
    list(make_json_request(json_list=args.data, address=args.address))
  )
