# Copyright 2025 Google LLC.
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

def _addr(value: str) -> tuple[str, int] | None:
  if not value:
    return None
  if ':' not in value:
    return None
  address_values = value.split(':')
  return (address_values[0], int(address_values[1]))


def add_command_line_args() -> argparse.ArgumentParser:
  """Adds command line args that can be passed to the CalloutServer constructor.

  Returns:
      argparse.ArgumentParser: Configured argument parser with callout server options.
  """
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--address',
      type=_addr,
      help='Address for the server with format: "0.0.0.0:443"',
  )
  parser.add_argument(
      '--port',
      type=int,
      help=
      'Port of the server, uses default_ip as the ip unless --address is specified.',
  )
  parser.add_argument(
      '--plaintext_address',
      type=_addr,
      help='Address for the plaintext (non grpc) server: "0.0.0.0:443"',
  )
  parser.add_argument(
      '--plaintext_port',
      type=int,
      help=
      'Plaintext port of the server, uses default_ip as the ip unless --plaintext_address is specified.',
  )
  parser.add_argument(
      '--health_check_address',
      type=_addr,
      help=('Health check address for the server with format: "0.0.0.0:80",' +
            'if False, no health check will be run.'),
  )
  parser.add_argument(
      '--health_check_port',
      type=int,
      help=
      'Health check port of the server, uses default_ip as the ip unless --health_check_address is specified.',
  )
  parser.add_argument(
      '--secure_health_check',
      action="store_true",
      help="Run a HTTPS health check rather than an HTTP one.",
  )
  parser.add_argument(
      '--combined_health_check',
      action="store_true",
      help="Do not create a seperate health check server.",
  )
  parser.add_argument(
      '--disable_plaintext',
      action="store_true",
      help='Disables the plaintext address of the callout server.',
  )
  return parser
