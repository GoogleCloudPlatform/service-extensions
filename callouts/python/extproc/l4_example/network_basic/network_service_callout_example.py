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
from typing import Tuple
from grpc import ServicerContext
from extproc.service import command_line_tools
from extproc.service.network_callout_server import NetworkCalloutServer

class BasicCalloutServer(NetworkCalloutServer):
  """Example callout server.

  A non-comprehensive set of examples for each of the possible callout actions.
  """

  def on_read_data(
      self,
      data: bytes,
      end_of_stream: bool,
      context: ServicerContext,
  ) -> Tuple[bytes, bool]:
    """Process data from client to server (read path).
    
    Override this method to implement custom processing logic.
    
    Args:
        data: Raw bytes from the client
        end_of_stream: Whether this is the last data frame
        context: gRPC context
        
    Returns:
        Tuple of (processed_data, modified)
    """
    # Default: pass through unchanged
    logging.debug("geting read data: %s, from ext_proc", data)
    return data, False

  def on_write_data(
      self,
      data: bytes,
      end_of_stream: bool,
      context: ServicerContext,
  ) -> Tuple[bytes, bool]:
    """Process data from server to client (write path).
    
    Override this method to implement custom processing logic.
    
    Args:
        data: Raw bytes from the server
        end_of_stream: Whether this is the last data frame
        context: gRPC context
        
    Returns:
        Tuple of (processed_data, modified)
    """

    logging.debug("geting write data: %s from ext_proc", data)
    # Default: pass through unchanged
    return data, False

if __name__ == '__main__':
  # Useful command line args.
  args = command_line_tools.add_command_line_args().parse_args()
  # Set the logging debug level.
  logging.basicConfig(level=logging.DEBUG)
  # Run the gRPC service.
  BasicCalloutServer(**vars(args)).run()
