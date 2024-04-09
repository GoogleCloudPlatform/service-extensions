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

def check_request_header(request_headers, header_key):
  """Check header of the request."""
  return next((header.key
                   for header in request_headers.headers.headers
                   if header.key == header_key), None)

def extract_jwt_token(context):
  metadata = dict(context.invocation_metadata())
  jwt_token = metadata.get('authorization')
  extracted_jwt = jwt_token.split(' ')[1] if jwt_token and ' ' in jwt_token else jwt_token
  return extracted_jwt

def validate_jwt_authorization(key, context, algorithm):
  jwt_token = extract_jwt_token(context)
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

  For the first validation it uses RS256 and is generated using the publickey
  from the project. On a request header it checks for a header '{header-rs}' if
  found then the validation for the RS256 happens, if the token is valid then
  the add mutation happens. A valid token example value can be found below.

  Valid Token for RS256:
  eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjY4Mzc1NywiZXhwIjoyMDc1NTYzNzU3fQ.eN4mB7iKBXFjqH-a-R5xyD0ZAT69UGlRx_DKYx2ehVG_JBOoEaVWxjyD8vVriuu1lOQ49WKzqIm5dGY8O-ccobWYZ38cmn69VfhSrqBQ3NIjD2cJer37H-FdTkqgiDtiRdg_rkxGRe0vznfoGQaXwjBnvRZgVpmWj4W2LLAbNN606Nl-boLDLodsDyPJEnD_jN7EOFjrpqGWLVosNnJmwaQfmCILz_q8t5BJe7ysr75xkBv5tta0HTpDoWsDmIR-qFNbpFHx_otgvabv4IE_X6yPBcjTupkMPw_DyVhm7tEBScXTQX-uT6NRJQ7BBaNEDPktkeCUm4QsIRVthen3xw

  For the second validation it uses HS256 and is generated using the Secret Key:
  'service-extensions'. On a request header it checks for a header '{header-hmac}'
  if found then the validation for the HS256 happens, if the token is valid then
  the add mutation happens. A valid token example value can be found below.

  Valid Token for HS256:
  eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjM1MTk5NywiZXhwIjoyMDc1MjMxOTk3fQ.sheYamXYaJsqRhTv1g_tyTbP9D7Q8Q3ANh2AgH7l46Q

  """

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders,
      context: ServicerContext):
    """Custom processor on request headers."""
    decoded = None
    if check_request_header(headers, "header-rs"):
      decoded = validate_jwt_authorization(self.public_key, context, "RS256")
    if check_request_header(headers, "header-hmac"):
      decoded = validate_jwt_authorization('service-extensions', context, "HS256")
    if decoded:
      decoded_items = [('decoded-' + key, str(value)) for key, value in decoded.items()]
      return callout_tools.add_header_mutation(add=decoded_items, clear_route_cache=True)
    else:
      callout_tools.deny_request(context, 'Authorization token is invalid')


if __name__ == '__main__':
  # Run the gRPC service
  CalloutServerExample(insecure_address=('0.0.0.0', 8080)).run()