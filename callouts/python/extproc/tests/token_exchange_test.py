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

"""Unit tests for the Token Exchange Python callout.

Pure unit tests: no gRPC server started, no real network calls. The process()
method is called directly with synthetic proto objects. HTTP calls to Google
STS (inbound mode) and external IdPs (outbound mode) are patched via
unittest.mock.patch.
"""

import base64
import hashlib
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.token_exchange.token_exchange_callout import TokenExchangeCallout


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _Ctx:
    """Minimal ServicerContext substitute that supports attribute assignment."""


def _make_jwt(claims: dict) -> str:
    """Build an unsigned JWT carrying the given claims (signature not verified by callout)."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(claims).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}."


def _make_callout(headers_dict: dict) -> service_pb2.ProcessingRequest:
    hm = HeaderMap()
    for k, v in headers_dict.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.ProcessingRequest(
        request_headers=service_pb2.HttpHeaders(headers=hm)
    )


def _mutated_headers(response: service_pb2.ProcessingResponse) -> dict:
    return {
        hvo.header.key: hvo.header.raw_value.decode()
        for hvo in response.request_headers.response.header_mutation.set_headers
    }


def _mock_http_response(access_token: str, expires_in: int | None = 3600) -> MagicMock:
    mock = MagicMock()
    body = {"access_token": access_token}
    if expires_in is not None:
        body["expires_in"] = expires_in
    mock.json.return_value = body
    mock.raise_for_status.return_value = None
    return mock


_SAMPLE_JWT = _make_jwt({
    "sub": "user-123",
    "email": "user@example.com",
    "groups": ["eng", "admin"],
})

_INBOUND_ENVS = {
    "TOKEN_EXCHANGE_MODE": "inbound",
    "WIF_POOL_ID": "test-pool",
    "WIF_PROVIDER_ID": "test-provider",
    "WIF_PROJECT_NUMBER": "123456789",
}

_OUTBOUND_ENVS = {
    "TOKEN_EXCHANGE_MODE": "outbound",
    "OUTBOUND_TOKEN_URL": "https://idp.example.com/token",
    "OUTBOUND_CLIENT_ID": "client-id",
    "OUTBOUND_CLIENT_SECRET": "client-secret",
}


@pytest.fixture(scope="module")
def svc_inbound():
    with patch.dict(os.environ, _INBOUND_ENVS):
        callout = TokenExchangeCallout(disable_tls=True, plaintext_address=("0.0.0.0", 0))
        try:
            yield callout
        finally:
            if callout._callout_server is not None:
                callout._callout_server.stop()


@pytest.fixture(scope="module")
def svc_outbound():
    with patch.dict(os.environ, _OUTBOUND_ENVS):
        callout = TokenExchangeCallout(disable_tls=True, plaintext_address=("0.0.0.0", 0))
        try:
            yield callout
        finally:
            if callout._callout_server is not None:
                callout._callout_server.stop()


# ---------------------------------------------------------------------------
# Pass-through: no / invalid Authorization header
# ---------------------------------------------------------------------------

class TestPassThrough:
    def test_no_auth_header(self, svc_inbound):
        result = svc_inbound.process(_make_callout({":path": "/api"}), _Ctx())
        assert not _mutated_headers(result)

    def test_non_bearer_scheme(self, svc_inbound):
        result = svc_inbound.process(
            _make_callout({"authorization": "Basic dXNlcjpwYXNz"}), _Ctx())
        assert not _mutated_headers(result)

    def test_bearer_without_token(self, svc_inbound):
        result = svc_inbound.process(
            _make_callout({"authorization": "Bearer"}), _Ctx())
        assert not _mutated_headers(result)


# ---------------------------------------------------------------------------
# Inbound: external JWT → Google access token via STS
# ---------------------------------------------------------------------------

class TestInboundExchange:
    def test_authorization_header_replaced(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("google-token")):
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert _mutated_headers(result)["authorization"] == "Bearer google-token"

    def test_sts_called_with_json_camelcase_payload(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")) as mock_post:
            svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        _, kwargs = mock_post.call_args
        # Google STS uses JSON with camelCase keys, not form-encoded snake_case
        assert "json" in kwargs
        assert kwargs["json"]["grantType"] == "urn:ietf:params:oauth:grant-type:token-exchange"
        assert kwargs["json"]["subjectToken"] == _SAMPLE_JWT
        assert kwargs["json"]["subjectTokenType"] == "urn:ietf:params:oauth:token-type:jwt"

    def test_sts_audience_contains_wif_identifiers(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")) as mock_post:
            svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        audience = mock_post.call_args[1]["json"]["audience"]
        assert "test-pool" in audience
        assert "test-provider" in audience
        assert "123456789" in audience

    def test_audit_email_header(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")):
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert _mutated_headers(result)["x-goog-authenticated-user-email"] == "user@example.com"

    def test_audit_user_id_header(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")):
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert _mutated_headers(result)["x-goog-authenticated-user-id"] == "user-123"

    def test_audit_groups_header_comma_separated(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")):
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert _mutated_headers(result)["x-original-user-groups"] == "eng,admin"

    def test_cache_hit_skips_sts_call(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")) as mock_post:
            svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
            assert mock_post.call_count == 1
            svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
            assert mock_post.call_count == 1  # cache HIT — no second call

    def test_cache_hit_returns_first_token(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("first-token")):
            svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        with patch("requests.post", return_value=_mock_http_response("second-token")):
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert _mutated_headers(result)["authorization"] == "Bearer first-token"

    def test_expired_cache_triggers_fresh_exchange(self, svc_inbound):
        svc_inbound.cache.clear()
        cache_key = hashlib.sha256(_SAMPLE_JWT.encode()).hexdigest()
        svc_inbound.cache[cache_key] = ("stale-token", int(time.time()) - 1)
        with patch("requests.post", return_value=_mock_http_response("fresh-token")) as mock_post:
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert mock_post.call_count == 1
        assert _mutated_headers(result)["authorization"] == "Bearer fresh-token"


# ---------------------------------------------------------------------------
# Outbound: Google JWT → external IdP token via RFC 8693
# ---------------------------------------------------------------------------

class TestOutboundExchange:
    def test_authorization_header_replaced(self, svc_outbound):
        svc_outbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("outbound-token")):
            result = svc_outbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert _mutated_headers(result)["authorization"] == "Bearer outbound-token"

    def test_idp_called_with_form_encoded_snake_case_payload(self, svc_outbound):
        svc_outbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")) as mock_post:
            svc_outbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        _, kwargs = mock_post.call_args
        # Outbound uses standard OAuth2 form-encoding with snake_case keys
        assert "data" in kwargs
        assert kwargs["data"]["grant_type"] == "urn:ietf:params:oauth:grant-type:token-exchange"
        assert kwargs["data"]["client_id"] == "client-id"
        assert kwargs["data"]["client_secret"] == "client-secret"

    def test_no_audit_headers_in_outbound_mode(self, svc_outbound):
        svc_outbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t")):
            result = svc_outbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        hdrs = _mutated_headers(result)
        assert "x-goog-authenticated-user-email" not in hdrs
        assert "x-goog-authenticated-user-id" not in hdrs
        assert "x-original-user-groups" not in hdrs

    def test_missing_expires_in_skips_caching(self, svc_outbound):
        svc_outbound.cache.clear()
        with patch("requests.post", return_value=_mock_http_response("t", expires_in=None)) as mock_post:
            svc_outbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
            svc_outbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert mock_post.call_count == 2  # no caching without expiry → always calls IdP


# ---------------------------------------------------------------------------
# Fail-open: any error must pass the request through unchanged
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_sts_http_error_passes_request_through(self, svc_inbound):
        svc_inbound.cache.clear()
        mock = MagicMock()
        mock.raise_for_status.side_effect = Exception("STS 500")
        with patch("requests.post", return_value=mock):
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert not _mutated_headers(result)

    def test_idp_http_error_passes_request_through(self, svc_outbound):
        svc_outbound.cache.clear()
        mock = MagicMock()
        mock.raise_for_status.side_effect = Exception("IdP 503")
        with patch("requests.post", return_value=mock):
            result = svc_outbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert not _mutated_headers(result)

    def test_network_error_passes_request_through(self, svc_inbound):
        svc_inbound.cache.clear()
        with patch("requests.post", side_effect=ConnectionError("timeout")):
            result = svc_inbound.process(
                _make_callout({"authorization": f"Bearer {_SAMPLE_JWT}"}), _Ctx())
        assert not _mutated_headers(result)


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

class TestConfigValidation:
    def test_inbound_missing_wif_pool_raises(self):
        with pytest.raises(ValueError, match="Missing inbound"):
            with patch.dict(os.environ, {
                "TOKEN_EXCHANGE_MODE": "inbound",
                "WIF_PROVIDER_ID": "p",
                "WIF_PROJECT_NUMBER": "123",
            }, clear=True):
                TokenExchangeCallout(disable_tls=True, plaintext_address=("0.0.0.0", 0))

    def test_inbound_missing_wif_provider_raises(self):
        with pytest.raises(ValueError, match="Missing inbound"):
            with patch.dict(os.environ, {
                "TOKEN_EXCHANGE_MODE": "inbound",
                "WIF_POOL_ID": "pool",
                "WIF_PROJECT_NUMBER": "123",
            }, clear=True):
                TokenExchangeCallout(disable_tls=True, plaintext_address=("0.0.0.0", 0))

    def test_outbound_missing_token_url_raises(self):
        with pytest.raises(ValueError, match="Missing outbound"):
            with patch.dict(os.environ, {
                "TOKEN_EXCHANGE_MODE": "outbound",
            }, clear=True):
                TokenExchangeCallout(disable_tls=True, plaintext_address=("0.0.0.0", 0))
