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
import os
import time
import logging
import hashlib
from typing import Optional, Tuple

import jwt
import requests
from cachetools import TTLCache

from extproc.service import callout_server
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption


class TokenExchangeCallout(callout_server.CalloutServer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = os.environ.get("TOKEN_EXCHANGE_MODE", "inbound").lower()
        self.cache = TTLCache(maxsize=10000, ttl=3600)
        
        self._init_inbound()
        self._init_outbound()

    def _init_inbound(self):
        self.wif_pool_id = os.environ.get("WIF_POOL_ID")
        self.wif_provider_id = os.environ.get("WIF_PROVIDER_ID")
        self.wif_project = os.environ.get("WIF_PROJECT_NUMBER")
        
        if self.mode == "inbound":
            if not all([self.wif_pool_id, self.wif_provider_id, self.wif_project]):
                logging.error("Inbound mode requires WIF_POOL_ID, WIF_PROVIDER_ID, WIF_PROJECT_NUMBER")
                raise ValueError("Missing inbound configuration")

    def _init_outbound(self):
        self.outbound_token_url = os.environ.get("OUTBOUND_TOKEN_URL")
        self.outbound_client_id = os.environ.get("OUTBOUND_CLIENT_ID")
        self.outbound_client_secret = os.environ.get("OUTBOUND_CLIENT_SECRET")
        
        if self.mode == "outbound" and not self.outbound_token_url:
            logging.error("Outbound mode requires OUTBOUND_TOKEN_URL")
            raise ValueError("Missing outbound configuration")

    def process(self, callout, context) -> service_pb2.ProcessingResponse:
        resp = super().process(callout, context)
        if resp.HasField("immediate_response"):
            return resp
        if callout.HasField("request_headers"):
            return self._on_request_headers(callout.request_headers, context)
        return resp

    def _on_request_headers(self, headers_msg, context) -> service_pb2.ProcessingResponse:
        auth_header = None
        for h in headers_msg.headers.headers:
            if h.key.lower() == "authorization":
                auth_header = h.raw_value.decode("utf-8").strip()
                break

        if not auth_header:
            return service_pb2.ProcessingResponse()

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logging.debug("Invalid Authorization header format. Passing through.")
            return service_pb2.ProcessingResponse()

        original_token = parts[1]
        cache_key = hashlib.sha256(original_token.encode("utf-8")).hexdigest()

        try:
            cached = self.cache.get(cache_key)
            if cached:
                new_token, expiry_ts = cached
                if expiry_ts - 60 > time.time():  # 60s safety margin before actual expiry
                    logging.info(f"[{self.mode.upper()}] Cache HIT.")
                    return self._build_response(new_token, original_token)

            logging.info(f"[{self.mode.upper()}] Cache MISS. Exchanging token.")
            if self.mode == "inbound":
                new_token, expiry_ts = self._exchange_inbound(original_token)
            else:
                new_token, expiry_ts = self._exchange_outbound(original_token)

            if expiry_ts:
                self.cache[cache_key] = (new_token, expiry_ts)

            return self._build_response(new_token, original_token)

        except Exception as e:
            logging.error(f"Exchange failed: {e}. Executing Fail-Open pass-through.")
            return service_pb2.ProcessingResponse()

    def _exchange_inbound(self, subject_token: str) -> Tuple[str, Optional[int]]:
        audience = f"//iam.googleapis.com/projects/{self.wif_project}/locations/global/workloadIdentityPools/{self.wif_pool_id}/providers/{self.wif_provider_id}"

        # Google STS REST API expects JSON with camelCase fields, unlike standard OAuth2 form-encoding.
        payload = {
            "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subjectToken": subject_token,
            "subjectTokenType": "urn:ietf:params:oauth:token-type:jwt",
            "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
            "audience": audience,
        }
        
        resp = requests.post("https://sts.googleapis.com/v1/token", json=payload, timeout=10.0)
        resp.raise_for_status()
        
        body = resp.json()
        return body["access_token"], int(time.time()) + body["expires_in"]

    def _exchange_outbound(self, subject_token: str) -> Tuple[str, Optional[int]]:
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
        if self.outbound_client_id: data["client_id"] = self.outbound_client_id
        if self.outbound_client_secret: data["client_secret"] = self.outbound_client_secret

        resp = requests.post(self.outbound_token_url, data=data, timeout=10.0)
        resp.raise_for_status()
        body = resp.json()
        expires_in = body.get("expires_in")
        return body["access_token"], int(time.time()) + expires_in if expires_in else None

    def _build_response(self, new_token: str, original_token: str) -> service_pb2.ProcessingResponse:
        resp = service_pb2.ProcessingResponse()
        mutations = resp.request_headers.response.header_mutation
        self._append_header(mutations, "authorization", f"Bearer {new_token}")

        if self.mode == "inbound":
            try:
                # Signature verification is intentionally skipped: we only extract claims
                # for downstream audit headers. The token was already validated by STS.
                decoded = jwt.decode(original_token, options={"verify_signature": False})
                email = decoded.get("email") or decoded.get("preferred_username")
                sub = decoded.get("sub")
                groups = decoded.get("groups")

                if email: self._append_header(mutations, "x-goog-authenticated-user-email", email)
                if sub: self._append_header(mutations, "x-goog-authenticated-user-id", sub)
                if groups:
                    groups_str = ",".join(groups) if isinstance(groups, list) else str(groups)
                    self._append_header(mutations, "x-original-user-groups", groups_str)
            except Exception as e:
                logging.warning(f"Audit headers bypass. Token decode failed: {e}")

        return resp

    @staticmethod
    def _append_header(mutation_obj, key: str, value: str) -> None:
        mutation_obj.set_headers.append(
            HeaderValueOption(
                header=HeaderValue(key=key, raw_value=value.encode("utf-8")),
                append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD
            )
        )
