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

"""Token Exchange callout: a pure ext_proc adapter.

The callout is intentionally thin: it inspects the inbound `Authorization`
header, exchanges the caller's token for a downstream-native credential (via
Google STS/Workload Identity Federation for inbound traffic, or a
third-party IdP's OAuth token endpoint for outbound traffic), and returns
the swap as a header mutation. No body phase is needed -- Token Exchange
never touches the request or response body -- so this callout only
implements `on_request_headers`, which keeps it on the fastest possible
path through the extension chain.

Routing model: this callout is attached as a Route or Traffic Extension on
an existing Application Load Balancer forwarding rule (or Agent Gateway
route), in front of a backend that already points at the real destination
(Vertex AI for inbound, the third-party API for outbound). The callout does
not choose the backend -- it only rewrites the credential presented to it.

`token_exchange` owns:
  * mode selection (INBOUND: 3rd-party token -> GCP access token via STS/WIF;
    OUTBOUND: GCP-minted JWT -> 3rd-party native token via that IdP)
  * a SHA-256-keyed token cache with a safety-margin TTL, so repeat callers
    don't pay a full STS/IdP round trip on every request
  * identity-preservation headers (`X-Goog-Authenticated-User-*`) for
    downstream audit logging

The callout owns:
  * Envoy ext_proc protobuf adapter (via `extproc.service.callout_server`)
  * `Authorization` header rewriting on the upstream call
  * fail-open vs fail-closed behavior on exchange errors
"""

import base64
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests
from grpc import ServicerContext

from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.service import callout_server
from extproc.service import callout_tools


# Identity-preservation headers stamped for downstream audit logging (design
# doc CUJ4: Secure Auditing of Federated Access). Downstream services should
# only trust these when the request signature confirms it passed through
# this callout's Load Balancer / Agent Gateway.
HEADER_AUDIT_EMAIL = "x-goog-authenticated-user-email"
HEADER_AUDIT_ID = "x-goog-authenticated-user-id"
HEADER_AUDIT_GROUPS = "x-original-user-groups"

STS_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
STS_REQUESTED_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
STS_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
IAM_GENERATE_ACCESS_TOKEN_URL = (
    "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{sa}:generateAccessToken"
)
GRANT_TYPE_JWT_BEARER = "urn:ietf:params:oauth:grant-type:jwt-bearer"


class TokenExchangeError(Exception):
    pass


@dataclass
class CachedToken:
    mutations: dict[str, str]  # full header mutation set, incl. audit headers
    expires_at: float  # epoch seconds, already adjusted by the safety margin


class TokenCache:
    """Thread-safe in-process cache, keyed by a SHA-256 hash of the source
    token (never the raw token, to avoid leaking it via memory dumps)."""

    def __init__(self):
        self._store: dict[str, CachedToken] = {}
        self._lock = threading.Lock()

    @staticmethod
    def key_for(source_token: str) -> str:
        return hashlib.sha256(source_token.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[CachedToken]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.time():
                del self._store[key]
                return None
            return entry

    def set(self, key: str, value: CachedToken) -> None:
        with self._lock:
            self._store[key] = value


def _decode_jwt_claims_unverified(jwt: str) -> dict:
    """Best-effort claim extraction for the audit headers ONLY.

    Not a substitute for verification -- the actual trust decision is made
    by STS (inbound) or the external IdP (outbound), both of which
    cryptographically validate the token against the configured trust
    relationship before this function is ever called. We only need
    `preferred_username`/`email`/`sub`/`groups` out of an already-trusted
    token to stamp onto audit headers.
    """
    try:
        parts = jwt.split(".")
        if len(parts) != 3:
            return {}
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:  # noqa: BLE001 -- claim extraction is best-effort
        return {}


class TokenExchangeCallout(callout_server.CalloutServer):
    """Ext_proc callout that swaps identity tokens at the networking layer."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode = os.getenv("TOKEN_EXCHANGE_MODE", "INBOUND").upper()
        self.fail_open = os.getenv("FAIL_OPEN", "true").lower() == "true"
        self.callout_timeout_seconds = float(os.getenv("CALLOUT_TIMEOUT_SECONDS", "10"))
        self.cache_safety_margin_seconds = int(os.getenv("CACHE_SAFETY_MARGIN_SECONDS", "60"))
        self.cache = TokenCache()
        self.session = requests.Session()

        # INBOUND (WIF/STS) settings.
        self.wif_audience = os.getenv("WIF_AUDIENCE", "")
        self.sts_endpoint = os.getenv("STS_ENDPOINT", "https://sts.googleapis.com/v1/token")
        self.requested_scope = os.getenv(
            "REQUESTED_SCOPE", "https://www.googleapis.com/auth/cloud-platform")
        self.target_service_account = os.getenv("TARGET_SERVICE_ACCOUNT", "")

        # OUTBOUND (external IdP) settings.
        self.external_token_endpoint = os.getenv("EXTERNAL_TOKEN_ENDPOINT", "")
        self.external_client_id = os.getenv("EXTERNAL_CLIENT_ID", "")

        if self.mode == "INBOUND" and not self.wif_audience:
            logging.warning(
                "TOKEN_EXCHANGE_MODE=INBOUND but WIF_AUDIENCE is unset; "
                "all inbound exchanges will fail.")
        if self.mode == "OUTBOUND" and not self.external_token_endpoint:
            logging.warning(
                "TOKEN_EXCHANGE_MODE=OUTBOUND but EXTERNAL_TOKEN_ENDPOINT is unset; "
                "all outbound exchanges will fail.")

    # ------------------------------------------------------------------ phase

    def on_request_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.ProcessingResponse | None:
        """Swap the Authorization header's token in place.

        Token Exchange never subscribes to the body, so this single phase
        handler is the entire callout.
        """
        auth_header = ""
        for h in headers.headers.headers:
            if h.key.lower() == "authorization":
                auth_header = (h.raw_value or h.value.encode("utf-8")).decode(
                    "utf-8", errors="replace")
                break

        if not auth_header.lower().startswith("bearer "):
            # Nothing to exchange -- let it fall through. IAM on the
            # backend remains responsible for rejecting unauthenticated
            # traffic; this callout only swaps credentials, it doesn't
            # enforce auth itself.
            return None

        source_token = auth_header[len("bearer "):].strip()
        cache_key = TokenCache.key_for(source_token)
        cached = self.cache.get(cache_key)

        try:
            if cached:
                mutations = cached.mutations
            elif self.mode == "INBOUND":
                mutations = self._exchange_inbound(source_token, cache_key)
            else:
                mutations = self._exchange_outbound(source_token, cache_key)
        except TokenExchangeError:
            logging.exception("token exchange failed")
            if self.fail_open:
                # Fail open: pass the original (unswapped) credential
                # through. The backend rejects it if it isn't valid there.
                return None
            return callout_tools.header_immediate_response(StatusCode.Unauthorized)

        resp = service_pb2.ProcessingResponse()
        for key, value in mutations.items():
            resp.request_headers.response.header_mutation.set_headers.append(
                HeaderValueOption(
                    header=HeaderValue(key=key, raw_value=value.encode("utf-8")),
                    append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
                ))
        return resp

    # -------------------------------------------------------------- exchange

    def _exchange_inbound(self, source_token: str, cache_key: str) -> dict[str, str]:
        """3rd-party OIDC token -> Google Cloud access token, via STS/WIF."""
        payload = {
            "grantType": STS_GRANT_TYPE,
            "audience": self.wif_audience,
            "scope": self.requested_scope,
            "requestedTokenType": STS_REQUESTED_TOKEN_TYPE,
            "subjectToken": source_token,
            "subjectTokenType": STS_SUBJECT_TOKEN_TYPE,
        }
        try:
            resp = self.session.post(
                self.sts_endpoint, json=payload, timeout=self.callout_timeout_seconds)
        except requests.RequestException as exc:
            raise TokenExchangeError(f"STS request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TokenExchangeError(
                f"STS exchange failed with status {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))

        if self.target_service_account:
            access_token, expires_in = self._impersonate_service_account(access_token)

        mutations = {"authorization": f"Bearer {access_token}"}
        claims = _decode_jwt_claims_unverified(source_token)
        email = claims.get("preferred_username") or claims.get("email")
        if email:
            mutations[HEADER_AUDIT_EMAIL] = email
        if claims.get("sub"):
            mutations[HEADER_AUDIT_ID] = claims["sub"]
        if claims.get("groups"):
            groups = claims["groups"]
            mutations[HEADER_AUDIT_GROUPS] = ",".join(groups) if isinstance(groups, list) else str(groups)

        self.cache.set(
            cache_key,
            CachedToken(
                mutations=mutations,
                expires_at=time.time() + expires_in - self.cache_safety_margin_seconds,
            ),
        )
        return mutations

    def _impersonate_service_account(self, federated_token: str) -> tuple[str, int]:
        url = IAM_GENERATE_ACCESS_TOKEN_URL.format(sa=self.target_service_account)
        headers = {"Authorization": f"Bearer {federated_token}"}
        payload = {"scope": [self.requested_scope], "lifetime": "3600s"}
        try:
            resp = self.session.post(
                url, json=payload, headers=headers, timeout=self.callout_timeout_seconds)
        except requests.RequestException as exc:
            raise TokenExchangeError(f"generateAccessToken request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TokenExchangeError(
                f"generateAccessToken failed with status {resp.status_code}: {resp.text[:500]}")
        return resp.json()["accessToken"], 3600

    def _exchange_outbound(self, source_token: str, cache_key: str) -> dict[str, str]:
        """Google-minted agent JWT -> 3rd-party native token (e.g. Salesforce)."""
        payload = {"grant_type": GRANT_TYPE_JWT_BEARER, "assertion": source_token}
        if self.external_client_id:
            payload["client_id"] = self.external_client_id
        try:
            resp = self.session.post(
                self.external_token_endpoint,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.callout_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise TokenExchangeError(f"external IdP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TokenExchangeError(
                f"external IdP exchange failed with status {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        native_token = data["access_token"]
        token_type = data.get("token_type", "Bearer")
        expires_in = int(data.get("expires_in", 3600))

        mutations = {"authorization": f"{token_type} {native_token}"}
        self.cache.set(
            cache_key,
            CachedToken(
                mutations=mutations,
                expires_at=time.time() + expires_in - self.cache_safety_margin_seconds,
            ),
        )
        return mutations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    TokenExchangeCallout(disable_tls=True).run()
