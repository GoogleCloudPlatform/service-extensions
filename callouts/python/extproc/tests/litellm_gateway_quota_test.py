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

import asyncio
import concurrent.futures
import json
import os
import time
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
import pytest

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.litellm_gateway import gateway_config
from extproc.example.litellm_gateway import quota
from extproc.example.litellm_gateway import seed_keys
from extproc.example.litellm_gateway import service_callout_example
from extproc.example.litellm_gateway.service_callout_example import (
    LiteLLMGatewayCallout,
    _ProviderRequest,
)


@pytest.fixture
def server():
    """One fake Redis instance behind both views below."""
    return fakeredis.FakeServer()


@pytest.fixture
def r(server):
    """Sync view, used by the seeder and by assertions."""
    return fakeredis.FakeRedis(decode_responses=True, server=server)


@pytest.fixture
def aio(server):
    """Async view of the same data. Quota talks to this one."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True, server=server)


@pytest.fixture
def q(aio):
    """A Quota bound to the fake Redis, with the safe defaults.

    Rate limits use an in-memory `limits` storage: fakeredis is not one of
    the backends `limits` speaks to, and the strategy under test is the
    same either way.
    """
    return quota.Quota(aio, rate_limiter=MovingWindowRateLimiter(
        MemoryStorage()))


def _seed(r, key, **fields):
    """Seed a key through the real seeder.

    Going through seed_keys.seed() rather than writing Redis fields by hand
    keeps these tests on the same validation and normalization path the
    deploy uses, so a change to the stored format cannot pass here and fail
    in production.
    """
    seed_keys.seed(r, [{"key": key, **fields}])


class _Ctx:
    pass


def _hdrs(d):
    hm = HeaderMap()
    for k, v in d.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.HttpHeaders(headers=hm)


def _svc(q=None):
    """A callout, optionally wired to the test's Quota.
    """
    with patch.dict(
        os.environ,
        {"GCP_PROJECT_ID": "p", "GCP_REGION": "us-central1"},
    ):
        svc = LiteLLMGatewayCallout(
            disable_tls=True, plaintext_address=("0.0.0.0", 0)
        )
    if q is not None:
        svc.quota = q
    return svc


KH = quota.key_hash("vk1")


@pytest.mark.asyncio
async def test_unknown_key_401(q):
    d = await q.check("nope", "anthropic/claude-haiku-4-5")
    assert (d.allowed, d.status) == (False, 401)


@pytest.mark.asyncio
async def test_empty_key_rejected_when_enabled(q):
    # A caller must not be able to evade its budget by dropping the
    # Authorization header, so an unauthenticated request is rejected.
    d = await q.check("", "anthropic/claude-haiku-4-5")
    assert (d.allowed, d.status) == (False, 401)


@pytest.mark.asyncio
async def test_empty_key_allowed_when_opted_in(r):
    # quota_allow_unauthenticated is the explicit opt-out, off by default.
    q = quota.Quota(r, gateway_config.QuotaSettings(
        fail_open=False, allow_unauthenticated=True))
    assert (await q.check("", "anthropic/claude-haiku-4-5")).allowed is True


@pytest.mark.asyncio
async def test_allow_within_limits(q, r):
    _seed(r, "k1", token_budget=1000, rpm_limit=10, budget_duration=30 * 86400)
    d = await q.check("k1", "anthropic/claude-haiku-4-5")
    assert d.allowed is True


@pytest.mark.asyncio
async def test_rpm_exceeded_429(q, r):
    _seed(r, "k2", rpm_limit=2)
    await q.check("k2", "m")
    await q.check("k2", "m")
    d = await q.check("k2", "m")
    assert (d.allowed, d.status) == (False, 429)


@pytest.mark.asyncio
async def test_one_redis_read_per_request(r, aio):
    # check(), usage_headers() and record() all need the key config, and a
    # request touches all three. Reading it once and passing it in is the
    # difference between one round trip per request and three.
    _seed(r, "vk1", token_budget=1000, budget_duration=30 * 86400,
          rpm_limit=60)
    reads = []
    real = aio.hgetall

    async def counting(*a, **k):
        reads.append(a)
        return await real(*a, **k)

    aio.hgetall = counting
    q = quota.Quota(aio)

    await q.check("vk1", "m")
    await q.usage_headers("vk1")
    await q.record("vk1", "m", 10)
    assert len(reads) == 3, "each call reads for itself when given no config"

    reads.clear()
    cfg = await q.key_config("vk1")
    await q.check("vk1", "m", cfg=cfg)
    await q.usage_headers("vk1", cfg=cfg)
    await q.record("vk1", "m", 10, cfg=cfg)
    assert len(reads) == 1, "the shared read is the only one"


@pytest.mark.asyncio
async def test_zero_rpm_limit_denies_everything(q, r):
    # An explicit 0 is a limit of zero, not "no limit". An operator setting
    # a limit to 0 is shutting the key off.
    _seed(r, "k-zero", rpm_limit=0)
    d = await q.check("k-zero", "m")
    assert (d.allowed, d.status) == (False, 429)


@pytest.mark.asyncio
async def test_zero_token_budget_denies_everything(q, r):
    _seed(r, "k-zero-budget", token_budget=0, budget_duration=30 * 86400)
    d = await q.check("k-zero-budget", "m")
    assert (d.allowed, d.status) == (False, 402)


@pytest.mark.asyncio
async def test_absent_limits_mean_unlimited(q, r):
    # A key with no limit fields at all is known and unrestricted, which is
    # what distinguishes it from the 0 case above.
    _seed(r, "k-open")
    for _ in range(5):
        assert (await q.check("k-open", "m")).allowed


class _Down:
    """A Redis whose every operation raises, as during an outage."""

    def __getattr__(self, name):
        async def boom(*a, **k):
            raise RuntimeError("redis down")
        return boom


def _drive_llm_request(svc):
    ctx = _Ctx()
    svc.on_request_headers(
        _hdrs({":path": "/v1/chat/completions", ":method": "POST",
               "authorization": "Bearer vk1"}), ctx)
    return svc.on_request_body(
        service_pb2.HttpBody(body=json.dumps({
            "model": "anthropic/claude-haiku-4-5",
            "messages": [],
        }).encode()), ctx)


def test_redis_outage_fails_open_when_configured():
    # The shared config read happens before check()'s own try/except.
    # Unguarded, an outage raised out of the gRPC handler and the operator
    # who chose availability (fail_open) got a 500 anyway.
    svc = _svc(quota.Quota(_Down(), gateway_config.QuotaSettings(
        fail_open=True, allow_unauthenticated=False)))
    try:
        with patch.object(
                svc, "_build_provider_request",
                side_effect=RuntimeError("stop before provider")):
            out = _drive_llm_request(svc)
        # Past quota entirely: the 500 comes from the patched transform,
        # not from a quota rejection.
        assert out.status.code == 500
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()


def test_redis_outage_fails_closed_with_a_clean_503():
    # Default config: the outage must surface as the intended immediate
    # 503, not as an uncaught exception from the handler.
    svc = _svc(quota.Quota(_Down()))
    try:
        out = _drive_llm_request(svc)
        assert out.status.code == 503
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()


def test_bridge_timeout_releases_the_worker_before_the_lb_gives_up():
    # The bridge timeout is a thread-pool safety net, so it only helps if
    # it fires before the load balancer abandons the request: ext_proc is
    # configured at 10s on the traffic extension and 5s on the route
    # extension. A value above those would park the worker past the point
    # where anything is listening, which is the drain it exists to prevent.
    assert service_callout_example._BRIDGE_TIMEOUT_S < 5.0 + 1e-9
    # And comfortably above a healthy call, bounded by socket_timeout=2.
    assert service_callout_example._BRIDGE_TIMEOUT_S > 2.0


def test_bridge_timeout_actually_fires_on_a_stuck_coroutine():
    import concurrent.futures
    bridge = service_callout_example._AsyncBridge()
    try:
        async def never():
            await asyncio.sleep(60)
        with pytest.raises(concurrent.futures.TimeoutError):
            bridge.run(never(), timeout=0.2)
    finally:
        bridge.close()


def test_bridge_serves_concurrent_sync_callers(r, server):
    # The ext_proc SDK is synchronous and serves on a thread pool, so many
    # threads drive the one bridge loop at once. asyncio.run() per call
    # cannot do this: it closes the loop while the connection pool outlives
    # it, which fails with "Event loop is closed" on real Redis.
    _seed(r, "vk1", rpm_limit=40)
    q = quota.Quota(
        fakeredis.aioredis.FakeRedis(decode_responses=True, server=server),
        rate_limiter=MovingWindowRateLimiter(MemoryStorage()))
    bridge = service_callout_example._AsyncBridge()
    try:
        def one(_):
            cfg = bridge.run(q.key_config("vk1"))
            return bridge.run(q.check("vk1", "m", cfg=cfg)).status

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            codes = list(pool.map(one, range(60)))
    finally:
        bridge.close()
    assert sum(1 for c in codes if c == 0) == 40
    assert sum(1 for c in codes if c == 429) == 20


@pytest.mark.asyncio
async def test_tpm_blocks_after_a_single_oversized_request(q, r):
    # One response can cost more than the whole per-minute allowance. This
    # is why tpm stays on a counter instead of `limits`: a rate limiter
    # refuses to record a hit larger than the limit, which would leave the
    # window empty and the limit unenforced.
    _seed(r, "k-big", tpm_limit=10)
    assert (await q.check("k-big", "m")).allowed
    await q.record("k-big", "m", 500)
    d = await q.check("k-big", "m")
    assert (d.allowed, d.status) == (False, 429)


@pytest.mark.asyncio
async def test_rpm_uses_a_moving_window_not_a_fixed_one(r, aio):
    # A fixed window refills the whole allowance at the minute boundary, so
    # a client straddling it can send 2x the limit. A moving window still
    # counts the earlier requests, so the limit holds across the boundary.
    _seed(r, "k-mw", rpm_limit=2)
    q = quota.Quota(aio, rate_limiter=MovingWindowRateLimiter(
        MemoryStorage()))
    assert (await q.check("k-mw", "m")).allowed
    assert (await q.check("k-mw", "m")).allowed
    assert (await q.check("k-mw", "m")).status == 429
    # Crossing into the next clock minute must not hand back a fresh
    # allowance while the earlier hits are still inside the window.
    with patch.object(quota.time, "time", return_value=time.time() + 31):
        assert (await q.check("k-mw", "m")).status == 429


@pytest.mark.asyncio
async def test_spend_counter_gets_a_ttl_on_first_write(q, r):
    # The increment and the expiry go out together, so the counter can
    # never be left without a TTL. The per-minute counters belong to
    # `limits` now and expire on its own schedule.
    _seed(r, "k-ttl", rpm_limit=10, token_budget=1000,
          budget_duration=30 * 86400)
    await q.check("k-ttl", "m")
    await q.record("k-ttl", "m", 5)
    kh = quota.key_hash("k-ttl")
    assert r.ttl(f"spend:{kh}:{quota._window_id(30 * 86400)}") > 0


@pytest.mark.asyncio
async def test_budget_exceeded_402(q, r):
    _seed(r, "k3", token_budget=100, budget_duration=30 * 86400)
    await q.record("k3", "m", 100)
    d = await q.check("k3", "m")
    assert (d.allowed, d.status) == (False, 402)


@pytest.mark.asyncio
async def test_record_increments_spend(q, r):
    _seed(r, "k4", token_budget=1000, budget_duration=30 * 86400)
    await q.record("k4", "m", 30)
    await q.record("k4", "m", 20)
    d = await q.check("k4", "m")
    assert d.allowed is True  # 50 < 1000


@pytest.mark.asyncio
async def test_fail_open_on_error():
    class Boom:
        def hgetall(self, *a, **k):
            raise RuntimeError("down")

    # Fail closed by default: LLM spend is expensive enough that rejecting
    # beats serving unmetered traffic when the backend is unreachable.
    closed = quota.Quota(Boom())
    d = await closed.check("k", "m")
    assert (d.allowed, d.status) == (False, 503)

    opened = quota.Quota(Boom(), gateway_config.QuotaSettings(
        fail_open=True, allow_unauthenticated=False))
    assert (await opened.check("k", "m")).allowed is True


@pytest.mark.asyncio
async def test_disabled_allows_all():
    # A Quota with no client is a working no-op, not a special case.
    inert = quota.Quota()
    assert inert.enabled() is False
    assert (await inert.check("anything", "m")).allowed is True
    await inert.record("anything", "m", 10)
    assert await inert.usage_headers("anything") == {}


def test_fail_open_default_comes_from_gateway_config(monkeypatch):
    # No QUOTA_FAIL_OPEN env var: the fail-open default should come from
    # the loaded gateway config file (general_settings.quota_fail_open),
    # not the module's hardcoded "true".
    monkeypatch.delenv("QUOTA_FAIL_OPEN", raising=False)
    monkeypatch.setenv("REDIS_HOST", "localhost")
    cfg = gateway_config.GatewayConfig.from_dict(
        {"general_settings": {"quota_fail_open": False}})
    assert quota.Quota.from_env(cfg.quota)._fail_open is False


def test_fail_open_env_garbage_fails_safe(monkeypatch):
    # Only the literal "true" enables fail-open. A typo like "0" or "no"
    # must not silently disable enforcement on a security switch.
    monkeypatch.setenv("REDIS_HOST", "localhost")
    for garbage in ("0", "no", "off", "yes", "TRUE "):
        monkeypatch.setenv("QUOTA_FAIL_OPEN", garbage)
        assert quota.Quota.from_env()._fail_open is False, garbage
    monkeypatch.setenv("QUOTA_FAIL_OPEN", "true")
    assert quota.Quota.from_env()._fail_open is True


def test_fail_open_env_overrides_config(monkeypatch):
    # Config says fail_open=False, but QUOTA_FAIL_OPEN=true is set in the
    # environment: the env var takes precedence over the config default.
    monkeypatch.setenv("QUOTA_FAIL_OPEN", "true")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    cfg = gateway_config.GatewayConfig.from_dict(
        {"general_settings": {"quota_fail_open": False}})
    assert quota.Quota.from_env(cfg.quota)._fail_open is True


@pytest.mark.asyncio
async def test_expired_key_rejected(q, r):
    _seed(r, "vk1", token_budget=1000, budget_duration=30 * 86400,
          expires="2020-01-01T00:00:00+00:00")
    decision = await q.check("vk1", "vertex_ai/gemini-2.5-flash")
    assert decision.status == 401
    assert "expired" in decision.reason


@pytest.mark.asyncio
async def test_future_expiry_allowed(q, r):
    _seed(r, "vk1", token_budget=1000, budget_duration=30 * 86400,
          expires="2099-01-01T00:00:00+00:00")
    assert (await q.check("vk1", "vertex_ai/gemini-2.5-flash")).allowed


@pytest.mark.asyncio
async def test_model_allowlist_blocks_other_models(q, r):
    _seed(r, "vk1", models=["anthropic/claude-haiku-4-5", "vertex_ai/*"])
    assert (await q.check("vk1", "anthropic/claude-haiku-4-5")).allowed
    assert (await q.check("vk1", "vertex_ai/gemini-2.5-pro")).allowed
    decision = await q.check("vk1", "groq/compound-beta")
    assert decision.status == 403
    assert "not allowed" in decision.reason


@pytest.mark.asyncio
async def test_model_allowlist_comma_string_is_normalized_at_seed_time(q, r):
    # A comma-separated allowlist is still accepted from keys.yaml, but it
    # is split once by the seeder. The request path only ever sees a JSON
    # array, so it does no format sniffing.
    _seed(r, "vk1", models="anthropic/claude-haiku-4-5, vertex_ai/*")
    assert r.hget(f"key:{KH}", "models") == (
        '["anthropic/claude-haiku-4-5", "vertex_ai/*"]')
    assert (await q.check("vk1", "vertex_ai/gemini-2.5-flash")).allowed
    assert (await q.check("vk1", "groq/compound-beta")).status == 403


@pytest.mark.asyncio
async def test_tpm_limit_enforced(q, r):
    _seed(r, "vk1", tpm_limit=100)
    assert (await q.check("vk1", "m")).allowed
    await q.record("vk1", "m", 100)
    decision = await q.check("vk1", "m")
    assert decision.status == 429
    assert "tpm" in decision.reason


@pytest.mark.asyncio
async def test_tpm_under_limit_allowed(q, r):
    _seed(r, "vk1", tpm_limit=100)
    await q.record("vk1", "m", 99)
    assert (await q.check("vk1", "m")).allowed


_MMB = {"anthropic/claude-haiku-4-5":
        {"budget_limit": 50, "time_period": 86400}}


@pytest.mark.asyncio
async def test_model_budget_enforced(q, r):
    _seed(r, "vk1", model_max_budget=_MMB)
    assert (await q.check("vk1", "anthropic/claude-haiku-4-5")).allowed
    await q.record("vk1", "anthropic/claude-haiku-4-5", 50)
    decision = await q.check("vk1", "anthropic/claude-haiku-4-5")
    assert decision.status == 402
    assert "model budget" in decision.reason


@pytest.mark.asyncio
async def test_model_budget_scoped_to_model(q, r):
    _seed(r, "vk1", model_max_budget=_MMB)
    await q.record("vk1", "anthropic/claude-haiku-4-5", 50)
    assert (await q.check("vk1", "vertex_ai/gemini-2.5-flash")).allowed


@pytest.mark.asyncio
async def test_model_spend_recorded_separately(q, r):
    _seed(r, "vk1", token_budget=1000, budget_duration=30 * 86400,
          model_max_budget=_MMB)
    await q.record("vk1", "anthropic/claude-haiku-4-5", 30)
    window = quota._window_id(86400)
    kh = quota.key_hash("vk1")
    per_model = r.get(
        f"spend:{kh}:anthropic/claude-haiku-4-5:{window}")
    assert int(per_model) == 30


def test_malformed_model_budget_is_rejected_at_seed_time(r):
    # This used to be silently dropped at read time, which meant a typo in a
    # budget config produced an unlimited model rather than an error.
    with pytest.raises(ValueError, match="model_max_budget"):
        _seed(r, "vk1", tpm_limit=100, model_max_budget={"m": 5})
    assert r.hgetall(f"key:{KH}") == {}


@pytest.mark.asyncio
async def test_soft_budget_warns_but_allows(q, r, caplog):
    _seed(r, "vk1", token_budget=1000, budget_duration=30 * 86400,
          soft_budget=50)
    await q.record("vk1", "m", 60)
    with caplog.at_level("WARNING"):
        assert (await q.check("vk1", "m")).allowed
    assert any("soft budget" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_usage_headers(q, r):
    _seed(r, "vk1", token_budget=1000, budget_duration=30 * 86400,
          rpm_limit=10)
    await q.record("vk1", "m", 100)
    await q.check("vk1", "m")  # consumes one rpm slot
    headers = await q.usage_headers("vk1")
    assert headers["x-litellm-key-spend"] == "100"
    assert headers["x-ratelimit-remaining-tokens"] == "900"
    assert headers["x-ratelimit-remaining-requests"] == "9"


@pytest.mark.asyncio
async def test_usage_headers_empty_for_unknown_or_keyless(q):
    assert await q.usage_headers("") == {}
    assert await q.usage_headers("nope") == {}


# ---------------------------------------------------------------------------
# B2: wiring tests (quota enforcement in the callout)
# ---------------------------------------------------------------------------

def test_over_budget_request_rejected(q, r):
    # Stays synchronous on purpose: it drives the ext_proc handlers, which
    # call asyncio.run() internally and so cannot run inside a live loop.
    _seed(r, "vk1", token_budget=100, budget_duration=30 * 86400)
    asyncio.run(q.record("vk1", "m", 100))
    svc = _svc(q)
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


def test_unknown_key_rejected_in_callout(q, r):
    svc = _svc(q)
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


def test_allowed_key_passes_through(q, r):
    _seed(r, "good_key", token_budget=50000, budget_duration=30 * 86400)
    pr = _ProviderRequest(
        api_base_url="https://api.anthropic.com/v1/messages",
        headers={"x-api-key": "k"},
        body={"x": 1},
        provider="anthropic",
        model="claude-haiku-4-5",
    )
    svc = _svc(q)
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
