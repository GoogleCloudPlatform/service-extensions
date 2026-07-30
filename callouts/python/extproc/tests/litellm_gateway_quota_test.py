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

"""Unit tests for quota enforcement. Uses fakeredis, no real Redis."""

import json
import os
import time
from unittest.mock import patch

import fakeredis
import pytest

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.litellm_gateway import gateway_config
from extproc.example.litellm_gateway import quota
from extproc.example.litellm_gateway.service_callout_example import (
    LiteLLMGatewayCallout,
    _ProviderRequest,
    _state,
)


@pytest.fixture
def r():
    client = fakeredis.FakeRedis(decode_responses=True)
    quota._set_client(client)
    yield client
    quota._reset()


def _seed(r, key, **fields):
    r.hset(f"key:{key}", mapping={k: str(v) for k, v in fields.items()})


class _Ctx:
    pass


def _hdrs(d):
    hm = HeaderMap()
    for k, v in d.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.HttpHeaders(headers=hm)


def _svc():
    with patch.dict(
        os.environ,
        {"GCP_PROJECT_ID": "p", "GCP_REGION": "us-central1"},
    ):
        return LiteLLMGatewayCallout(
            disable_tls=True, plaintext_address=("0.0.0.0", 0)
        )


def test_unknown_key_401(r):
    d = quota.check("nope", "anthropic/claude-haiku-4-5")
    assert (d.allowed, d.status) == (False, 401)


def test_empty_key_allowed_when_enabled(r):
    # Quota is opt-in: a request with no virtual key passes through unmetered
    # even when quota is enabled, so keyless clients are not blocked.
    d = quota.check("", "anthropic/claude-haiku-4-5")
    assert d.allowed is True


def test_allow_within_limits(r):
    _seed(r, "k1", token_budget=1000, rpm_limit=10, budget_duration="30d")
    d = quota.check("k1", "anthropic/claude-haiku-4-5")
    assert d.allowed is True


def test_rpm_exceeded_429(r):
    _seed(r, "k2", rpm_limit=2)
    quota.check("k2", "m")
    quota.check("k2", "m")
    d = quota.check("k2", "m")
    assert (d.allowed, d.status) == (False, 429)


def test_budget_exceeded_402(r):
    _seed(r, "k3", token_budget=100, budget_duration="30d")
    quota.record("k3", "m", 100)
    d = quota.check("k3", "m")
    assert (d.allowed, d.status) == (False, 402)


def test_record_increments_spend(r):
    _seed(r, "k4", token_budget=1000, budget_duration="30d")
    quota.record("k4", "m", 30)
    quota.record("k4", "m", 20)
    d = quota.check("k4", "m")
    assert d.allowed is True  # 50 < 1000


def test_fail_open_on_error(r):
    class Boom:
        def hgetall(self, *a, **k):
            raise RuntimeError("down")
    quota._set_client(Boom())
    d = quota.check("k", "m")
    assert d.allowed is True  # fail-open default


def test_disabled_allows_all():
    quota._reset()
    assert quota.enabled() is False
    assert quota.check("anything", "m").allowed is True


def test_fail_open_default_comes_from_gateway_config(monkeypatch):
    # No QUOTA_FAIL_OPEN env var: the fail-open default should come from
    # the loaded gateway config file (general_settings.quota_fail_open),
    # not the module's hardcoded "true".
    monkeypatch.delenv("QUOTA_FAIL_OPEN", raising=False)
    monkeypatch.setenv("REDIS_HOST", "localhost")
    gateway_config._load_dict(
        {"general_settings": {"quota_fail_open": False}})
    quota._reset()
    try:
        quota.init_client()
        assert quota._fail_open is False
    finally:
        quota._reset()
        gateway_config._reset()


def test_fail_open_env_overrides_config(monkeypatch):
    # Config says fail_open=False, but QUOTA_FAIL_OPEN=true is set in the
    # environment: the env var takes precedence over the config default.
    monkeypatch.setenv("QUOTA_FAIL_OPEN", "true")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    gateway_config._load_dict(
        {"general_settings": {"quota_fail_open": False}})
    quota._reset()
    try:
        quota.init_client()
        assert quota._fail_open is True
    finally:
        quota._reset()
        gateway_config._reset()


def test_expired_key_rejected(r):
    r.hset("key:vk1", mapping={
        "token_budget": 1000, "budget_duration": "30d",
        "expires": "2020-01-01T00:00:00+00:00"})
    decision = quota.check("vk1", "vertex_ai/gemini-2.5-flash")
    assert decision.status == 401
    assert "expired" in decision.reason


def test_future_expiry_allowed(r):
    r.hset("key:vk1", mapping={
        "token_budget": 1000, "budget_duration": "30d",
        "expires": "2099-01-01T00:00:00+00:00"})
    assert quota.check("vk1", "vertex_ai/gemini-2.5-flash").allowed


def test_model_allowlist_blocks_other_models(r):
    r.hset("key:vk1", mapping={
        "models": '["anthropic/claude-haiku-4-5", "vertex_ai/*"]'})
    assert quota.check("vk1", "anthropic/claude-haiku-4-5").allowed
    assert quota.check("vk1", "vertex_ai/gemini-2.5-pro").allowed
    decision = quota.check("vk1", "groq/compound-beta")
    assert decision.status == 403
    assert "not allowed" in decision.reason


def test_model_allowlist_comma_string(r):
    r.hset("key:vk1", mapping={
        "models": "anthropic/claude-haiku-4-5, vertex_ai/*"})
    assert quota.check("vk1", "vertex_ai/gemini-2.5-flash").allowed
    assert quota.check("vk1", "groq/compound-beta").status == 403


def test_month_window_unit(r):
    assert quota._window_seconds("1mo") == 30 * 86400


def test_tpm_limit_enforced(r):
    r.hset("key:vk1", mapping={"tpm_limit": 100})
    assert quota.check("vk1", "m").allowed
    quota.record("vk1", "m", 100)
    decision = quota.check("vk1", "m")
    assert decision.status == 429
    assert "tpm" in decision.reason


def test_tpm_under_limit_allowed(r):
    r.hset("key:vk1", mapping={"tpm_limit": 100})
    quota.record("vk1", "m", 99)
    assert quota.check("vk1", "m").allowed


_MMB = ('{"anthropic/claude-haiku-4-5": '
        '{"budget_limit": 50, "time_period": "1d"}}')


def test_model_budget_enforced(r):
    r.hset("key:vk1", mapping={"model_max_budget": _MMB})
    assert quota.check("vk1", "anthropic/claude-haiku-4-5").allowed
    quota.record("vk1", "anthropic/claude-haiku-4-5", 50)
    decision = quota.check("vk1", "anthropic/claude-haiku-4-5")
    assert decision.status == 402
    assert "model budget" in decision.reason


def test_model_budget_scoped_to_model(r):
    r.hset("key:vk1", mapping={"model_max_budget": _MMB})
    quota.record("vk1", "anthropic/claude-haiku-4-5", 50)
    assert quota.check("vk1", "vertex_ai/gemini-2.5-flash").allowed


def test_model_spend_recorded_separately(r):
    r.hset("key:vk1", mapping={
        "token_budget": 1000, "budget_duration": "30d",
        "model_max_budget": _MMB})
    quota.record("vk1", "anthropic/claude-haiku-4-5", 30)
    window = quota._window_id("1d")
    per_model = quota._client.get(
        f"spend:vk1:anthropic/claude-haiku-4-5:{window}")
    assert int(per_model) == 30


def test_malformed_model_budget_entry_ignored(r):
    r.hset("key:vk1", mapping={
        "tpm_limit": 100, "model_max_budget": '{"m": 5}'})
    assert quota.check("vk1", "m").allowed
    quota.record("vk1", "m", 10)
    minute = int(time.time()) // 60
    assert int(r.get(f"tpm:vk1:{minute}")) == 10


def test_soft_budget_warns_but_allows(r, caplog):
    r.hset("key:vk1", mapping={
        "token_budget": 1000, "budget_duration": "30d", "soft_budget": 50})
    quota.record("vk1", "m", 60)
    with caplog.at_level("WARNING"):
        assert quota.check("vk1", "m").allowed
    assert any("soft budget" in r.message for r in caplog.records)


def test_usage_headers(r):
    r.hset("key:vk1", mapping={
        "token_budget": 1000, "budget_duration": "30d", "rpm_limit": 10})
    quota.record("vk1", "m", 100)
    quota.check("vk1", "m")  # consumes one rpm slot
    headers = quota.usage_headers("vk1")
    assert headers["x-litellm-key-spend"] == "100"
    assert headers["x-ratelimit-remaining-tokens"] == "900"
    assert headers["x-ratelimit-remaining-requests"] == "9"


def test_usage_headers_empty_for_unknown_or_keyless(r):
    assert quota.usage_headers("") == {}
    assert quota.usage_headers("nope") == {}


# ---------------------------------------------------------------------------
# B2: wiring tests (quota enforcement in the callout)
# ---------------------------------------------------------------------------

def test_over_budget_request_rejected(r):
    r.hset(
        "key:vk1",
        mapping={"token_budget": "100", "budget_duration": "30d"},
    )
    quota.record("vk1", "m", 100)
    svc = _svc()
    try:
        ctx = _Ctx()
        svc.on_request_headers(
            _hdrs({
                ":path": "/v1/chat/completions",
                ":method": "POST",
                "authorization": "Bearer vk1",
            }),
            ctx,
        )
        out = svc.on_request_body(
            service_pb2.HttpBody(
                body=json.dumps({
                    "model": "anthropic/claude-haiku-4-5",
                    "messages": [],
                }).encode()
            ),
            ctx,
        )
        # header_immediate_response returns ImmediateResponse directly;
        # on_request_body returns it as-is. Attribute path: out.status.code
        assert out.status.code == 402
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()


def test_unknown_key_rejected_in_callout(r):
    svc = _svc()
    try:
        ctx = _Ctx()
        svc.on_request_headers(
            _hdrs({
                ":path": "/v1/chat/completions",
                ":method": "POST",
                "authorization": "Bearer no_such_key",
            }),
            ctx,
        )
        out = svc.on_request_body(
            service_pb2.HttpBody(
                body=json.dumps({
                    "model": "anthropic/claude-haiku-4-5",
                    "messages": [],
                }).encode()
            ),
            ctx,
        )
        assert out.status.code == 401
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()


def test_allowed_key_passes_through(r):
    r.hset(
        "key:good_key",
        mapping={"token_budget": "50000", "budget_duration": "30d"},
    )
    pr = _ProviderRequest(
        api_base_url="https://api.anthropic.com/v1/messages",
        headers={"x-api-key": "k"},
        body={"x": 1},
        provider="anthropic",
        model="claude-haiku-4-5",
    )
    svc = _svc()
    try:
        ctx = _Ctx()
        svc.on_request_headers(
            _hdrs({
                ":path": "/v1/chat/completions",
                ":method": "POST",
                "authorization": "Bearer good_key",
            }),
            ctx,
        )
        with patch.object(svc, "_build_provider_request", return_value=pr):
            out = svc.on_request_body(
                service_pb2.HttpBody(
                    body=json.dumps({
                        "model": "anthropic/claude-haiku-4-5",
                        "messages": [],
                    }).encode()
                ),
                ctx,
            )
        # Should NOT be an ImmediateResponse; should be a BodyResponse.
        assert not hasattr(out, "status") or out.status.code == 0
        assert hasattr(out, "response")
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()
