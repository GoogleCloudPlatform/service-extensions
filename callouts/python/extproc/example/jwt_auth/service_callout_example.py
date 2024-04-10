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
import jwt
from jwt.exceptions import InvalidTokenError

from grpc import ServicerContext
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from extproc.service import callout_server
from extproc.service import callout_tools

def extract_jwt_token(request_headers):
  jwt_token = next((header.raw_value.decode('utf-8')
                   for header in request_headers.headers.headers
                   if header.key == 'Authorization'), None)
  extracted_jwt = jwt_token.split(' ')[1] if jwt_token and ' ' in jwt_token else jwt_token
  return extracted_jwt

def validate_jwt_token(key, request_headers, algorithm):
  jwt_token = extract_jwt_token(request_headers)
  try:
    decoded = jwt.decode(jwt_token, key, algorithms=[algorithm])
    logging.info('Approved - Decoded Values: %s', decoded)
    return decoded
  except InvalidTokenError:
    return None

class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server.

  For request header callouts we provide a mutation to add multiple headers
  based on the decoded fields for example '{decoded-name: John Doe}', and to
  clear the route cache if the JWT Authorization is valid.
  A valid token example value can be found below.

  Valid Token for RS256:
  eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjc3Njc2MSwiZXhwIjoyMDc1NjU2NzYxfQ.BSH8s_MexJJYrFqKld-PwaUu3ovXu-ZfBcfsqiFtWQVHtcJu1Q0PHFLfBSx_9Uu57Uzfj2DoALVe-rF7VZoBfB-gFSbNVSneF7kLrpVD_E84ItZINzBqta5UyTdO0T4PHZtB9m_lmZq-u9IPUNF4h_GeWKRAEVwxzp46szBytFuAIEW0mlIoKxYUSlaHxCLqXz9tYyGJe9ZQpBp_tLRnvQslE6ZqsvGuhIJya1HAFy_pf9jmPswufXp5y5m2j3LQ7fcGh8p7cFBWM2mKycjpY420dbuiQcu0MPx2qqkrJuVDx4E9mcXBsdqVUufEnqTPzKnwwHS_mOst9t3kBTXLPg

  """

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext):
    """Custom processor on request headers."""

    decoded = validate_jwt_token(self.public_key, headers, "RS256")

    if decoded:
      decoded_items = [('decoded-' + key, str(value)) for key, value in decoded.items()]
      return callout_tools.add_header_mutation(add=decoded_items, clear_route_cache=True)
    else:
      callout_tools.deny_request(context, 'Authorization token is invalid')


if __name__ == '__main__':
  # Run the gRPC service
  CalloutServerExample(insecure_address=('0.0.0.0', 8080)).run()