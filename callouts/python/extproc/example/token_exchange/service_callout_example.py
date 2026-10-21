# Copyright 2026 Google LLC.
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

import hashlib
import logging
import os
import threading
import time
from typing import Optional, Tuple, Union

from cachetools import TTLCache
from envoy.config.core.v3.base_pb2 import HeaderValueOption
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode
from grpc import ServicerContext
import jwt
import requests

from extproc.service import callout_server
from extproc.service import callout_tools
from extproc.service import command_line_tools

_STS_TOKEN_URL = 'https://sts.googleapis.com/v1/token'
_DEFAULT_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
_GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:token-exchange'
_JWT_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:jwt'
_ACCESS_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:access_token'

_AGENT_USER_AUTH_HEADER = 'x-goog-agent-user-authorization'
_EMAIL_HEADER = 'x-goog-authenticated-user-email'
_USER_ID_HEADER = 'x-goog-authenticated-user-id'
_GROUPS_HEADER = 'x-original-user-groups'
# Identity headers owned by this callout server in inbound mode. Any copy sent
# by the client is removed, so the backend can trust that they are only present
# on requests whose token was successfully exchanged.
_IDENTITY_HEADERS = (_EMAIL_HEADER, _USER_ID_HEADER, _GROUPS_HEADER)

_TRUE_VALUES = ('1', 'true', 'yes')


class CalloutServerExample(callout_server.CalloutServer):
  """Example callout server that exchanges bearer tokens.

  For request header callouts the bearer token in the 'Authorization' header
  is exchanged for a new one, which replaces the original.

  The behavior is configured with environment variables:

  * TOKEN_EXCHANGE_MODE: 'inbound' (default) exchanges an external JWT for a
    Google access token using Workload Identity Federation. 'outbound'
    exchanges the token at an external RFC 8693 token endpoint.
  * TOKEN_EXCHANGE_FAIL_CLOSED: if true, requests that were not successfully
    exchanged are rejected instead of being passed through unchanged.
  * WIF_PROJECT_NUMBER, WIF_POOL_ID, WIF_PROVIDER_ID: required in inbound mode.
  * WIF_SCOPE: OAuth scopes of the Google access token, space separated.
    Defaults to the cloud-platform scope.
  * OUTBOUND_TOKEN_URL: required in outbound mode.
  * OUTBOUND_CLIENT_ID, OUTBOUND_CLIENT_SECRET: optional in outbound mode.
  """

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.mode = os.environ.get('TOKEN_EXCHANGE_MODE', 'inbound').lower()
    if self.mode not in ('inbound', 'outbound'):
      raise ValueError(f'Unknown TOKEN_EXCHANGE_MODE: {self.mode}')
    self.fail_closed = os.environ.get(
        'TOKEN_EXCHANGE_FAIL_CLOSED', 'false').lower() in _TRUE_VALUES
    self.cache = TTLCache(maxsize=10000, ttl=3600)
    # The base server handles callouts on several threads, and TTLCache is not
    # thread-safe. The lock covers the cache accesses only, not the exchange.
    self.cache_lock = threading.Lock()
    # Shared session, so that exchanges reuse pooled connections instead of
    # paying for a TLS handshake on every request.
    self.session = requests.Session()

    self._init_inbound()
    self._init_outbound()

  def _init_inbound(self) -> None:
    self.wif_pool_id = os.environ.get('WIF_POOL_ID')
    self.wif_provider_id = os.environ.get('WIF_PROVIDER_ID')
    self.wif_project = os.environ.get('WIF_PROJECT_NUMBER')
    self.wif_scope = os.environ.get('WIF_SCOPE') or _DEFAULT_SCOPE

    if self.mode == 'inbound' and not all(
        [self.wif_pool_id, self.wif_provider_id, self.wif_project]):
      logging.error('Inbound mode requires WIF_POOL_ID, WIF_PROVIDER_ID, '
                    'WIF_PROJECT_NUMBER')
      raise ValueError('Missing inbound configuration')

  def _init_outbound(self) -> None:
    self.outbound_token_url = os.environ.get('OUTBOUND_TOKEN_URL')
    self.outbound_client_id = os.environ.get('OUTBOUND_CLIENT_ID')
    self.outbound_client_secret = os.environ.get('OUTBOUND_CLIENT_SECRET')

    if self.mode == 'outbound' and not self.outbound_token_url:
      logging.error('Outbound mode requires OUTBOUND_TOKEN_URL')
      raise ValueError('Missing outbound configuration')

  def on_request_headers(
      self, headers: service_pb2.HttpHeaders, context: ServicerContext
  ) -> Union[service_pb2.HeadersResponse, service_pb2.ImmediateResponse]:
    """Exchange the bearer token and replace the 'Authorization' header.

    See base method:
    :py:meth:`callouts.python.extproc.service.callout_server.CalloutServer.on_request_headers`.
    """
    original_token = _extract_bearer_token(headers)
    if original_token is None:
      logging.debug('No bearer token in the Authorization header.')
      return self._not_exchanged(StatusCode.Unauthorized,
                                 'missing_bearer_token')

    try:
      new_token = self._get_exchanged_token(original_token)
    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.error('Exchange failed: %s. Executing %s.', e,
                    'fail-closed denial'
                    if self.fail_closed else 'fail-open pass-through')
      return self._not_exchanged(StatusCode.Forbidden, 'token_exchange_failed')

    return self._build_response(new_token, original_token)

  def _get_exchanged_token(self, original_token: str) -> str:
    """Returns the exchanged token, from the cache when still valid."""
    cache_key = hashlib.sha256(original_token.encode('utf-8')).hexdigest()
    with self.cache_lock:
      cached = self.cache.get(cache_key)
    if cached:
      new_token, expiry_ts = cached
      # 60s safety margin before actual expiry.
      if expiry_ts - 60 > time.time():
        logging.info('[%s] Cache HIT.', self.mode.upper())
        return new_token

    logging.info('[%s] Cache MISS. Exchanging token.', self.mode.upper())
    if self.mode == 'inbound':
      new_token, expiry_ts = self._exchange_inbound(original_token)
    else:
      new_token, expiry_ts = self._exchange_outbound(original_token)

    if expiry_ts:
      with self.cache_lock:
        self.cache[cache_key] = (new_token, expiry_ts)
    return new_token

  def _exchange_inbound(self, subject_token: str) -> Tuple[str, Optional[int]]:
    audience = (
        f'//iam.googleapis.com/projects/{self.wif_project}/locations/global/'
        f'workloadIdentityPools/{self.wif_pool_id}/'
        f'providers/{self.wif_provider_id}')

    # Google STS REST API expects JSON with camelCase fields, unlike standard
    # OAuth2 form-encoding.
    payload = {
        'grantType': _GRANT_TYPE,
        'subjectToken': subject_token,
        'subjectTokenType': _JWT_TOKEN_TYPE,
        'requestedTokenType': _ACCESS_TOKEN_TYPE,
        # STS rejects exchanges that do not request a scope.
        'scope': self.wif_scope,
        'audience': audience,
    }

    resp = self.session.post(_STS_TOKEN_URL, json=payload, timeout=10.0)
    resp.raise_for_status()

    body = resp.json()
    expiry_ts = int(time.time()) + int(body['expires_in'])
    return body['access_token'], expiry_ts

  def _exchange_outbound(self, subject_token: str) -> Tuple[str, Optional[int]]:
    data = {
        'grant_type': _GRANT_TYPE,
        'subject_token': subject_token,
        'subject_token_type': _JWT_TOKEN_TYPE,
        'requested_token_type': _ACCESS_TOKEN_TYPE,
    }
    if self.outbound_client_id:
      data['client_id'] = self.outbound_client_id
    if self.outbound_client_secret:
      data['client_secret'] = self.outbound_client_secret

    resp = self.session.post(self.outbound_token_url, data=data, timeout=10.0)
    resp.raise_for_status()

    body = resp.json()
    expires_in = body.get('expires_in')
    expiry_ts = int(time.time()) + int(expires_in) if expires_in else None
    return body['access_token'], expiry_ts

  def _not_exchanged(
      self, code: StatusCode, details: str
  ) -> Union[service_pb2.HeadersResponse, service_pb2.ImmediateResponse]:
    """Response for a request whose token was not exchanged.

    Fail-closed: reject the request with the given status code.
    Fail-open: pass the request through. In inbound mode the identity headers
    are still removed, because the request was not authenticated.
    """
    if self.fail_closed:
      response = callout_tools.header_immediate_response(code=code)
      response.details = details
      return response
    if self.mode == 'inbound':
      return callout_tools.add_header_mutation(
          remove=[*_IDENTITY_HEADERS, _AGENT_USER_AUTH_HEADER])
    return service_pb2.HeadersResponse()

  def _build_response(
      self, new_token: str, original_token: str
  ) -> service_pb2.HeadersResponse:
    add = [('authorization', f'Bearer {new_token}')]
    remove = []

    if self.mode == 'inbound':
      add.append((_AGENT_USER_AUTH_HEADER, f'Bearer {original_token}'))
      identity = _identity_headers(original_token)
      add.extend(identity.items())
      # Remove the identity headers that have no matching claim, so that
      # values supplied by the client never reach the backend.
      remove = [h for h in _IDENTITY_HEADERS if h not in identity]

    return callout_tools.add_header_mutation(
        add=add,
        remove=remove,
        append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
    )


def _extract_bearer_token(headers: service_pb2.HttpHeaders) -> Optional[str]:
  """Returns the token of an 'Authorization: Bearer <token>' header."""
  for header in headers.headers.headers:
    if header.key.lower() == 'authorization':
      # Envoy sends either raw_value or value. A raw_value that is not valid
      # UTF-8 must not raise: the callout would fail before the identity
      # headers are removed from the request.
      raw = (header.raw_value.decode('utf-8', errors='replace')
             if header.raw_value else header.value)
      parts = (raw or '').split()
      if len(parts) == 2 and parts[0].lower() == 'bearer':
        return parts[1]
      return None
  return None


def _identity_headers(token: str) -> dict[str, str]:
  """Builds the identity headers from the claims of an exchanged JWT."""
  try:
    # Signature verification is intentionally skipped: we only extract claims
    # for downstream audit headers. The token was already validated by STS.
    claims = jwt.decode(token, options={'verify_signature': False})
  except Exception as e:  # pylint: disable=broad-exception-caught
    logging.warning('Audit headers bypass. Token decode failed: %s', e)
    return {}

  identity = {}
  email = claims.get('email') or claims.get('preferred_username')
  if email:
    identity[_EMAIL_HEADER] = str(email)
  sub = claims.get('sub')
  if sub:
    identity[_USER_ID_HEADER] = str(sub)
  groups = claims.get('groups')
  if groups:
    if isinstance(groups, list):
      groups = ','.join(str(group) for group in groups)
    identity[_GROUPS_HEADER] = str(groups)
  return identity


if __name__ == '__main__':
  # Useful command line args.
  args = command_line_tools.add_command_line_args().parse_args()
  # Set the logging level.
  logging.basicConfig(
      level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
  # Run the gRPC service.
  CalloutServerExample(**vars(args)).run()
