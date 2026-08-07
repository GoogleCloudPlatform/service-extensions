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

"""Token budget and rate-limit enforcement backed by Redis (Memorystore).

Env-gated: inert unless REDIS_HOST is set. Two-phase, matching the two
ext_proc legs: check() on the request leg (pre-check), record() on the
response leg.
A single Redis instance holds key config, spend counters, and rate counters;
this sample does not consider the Proxy's Postgres plus Redis split.

`rpm_limit` is delegated to `limits`, which counts server-side and uses a
moving window, so straddling a minute boundary cannot buy a second
allowance.

`tpm_limit` and the token budgets stay here. They are budgets rather than
rates: one request can cost more than the whole per-minute allowance, and
`limits` refuses to record a hit whose cost exceeds the limit, which would
leave the window empty and the limit unenforced. A plain counter can go
over and block the next request, which is the behavior wanted.

Virtual keys are credentials, so they are never stored in Redis verbatim:
every Redis key name is built from `key_hash()`, a SHA-256 of the virtual
key. A dump of the datastore therefore reveals usage but not the keys
themselves. `seed_keys.py` writes the same hashes.

Each `key:<key hash>` Redis hash may carry: `token_budget`, `rpm_limit`,
`tpm_limit`, `soft_budget` (integers), `budget_duration` (whole seconds),
`models` (JSON array), `model_max_budget` (JSON object), and `expires` (a
timezone-aware UTC ISO-8601 timestamp).

Windows are seconds in keys.yaml, in Redis and here, so no unit is ever
parsed or converted. `expires` is written in any ISO-8601 form and pinned to
UTC by `seed_keys.py`, which validates every field on the way in: a value
that cannot be stored fails the seed run instead of surfacing on a live
request.

For any limit field, an absent field means unlimited and an explicit 0
means zero allowed.

When quota is enabled, a request that presents no virtual key is rejected
with 401. Set `general_settings.quota_allow_unauthenticated` (or
`QUOTA_ALLOW_UNAUTHENTICATED`) to let unauthenticated requests through
unmetered; that is off by default because otherwise any caller could evade
its budget simply by dropping the Authorization header.

`model_max_budget` maps a model name to `{"budget_limit": <tokens>,
"time_period": <seconds>}` (LiteLLM's /key/generate parameter shape, with
the period given in seconds). Spend
against each entry is tracked separately from the key-level budget, in
`spend:<key hash>:<model>:<window_id>` keys written by record().

`soft_budget` is a warn-only threshold below `token_budget`: check() logs a
warning once spend reaches it but still allows the request. usage_headers()
returns LiteLLM-named response headers (key spend, remaining tokens,
remaining requests) computed from the same counters, for callers that want
to surface quota state to clients without a hard block.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, NamedTuple, Optional

import redis.asyncio as redis
from limits import RateLimitItemPerMinute
from limits.aio.storage import MemoryStorage, RedisStorage
from limits.aio.strategies import MovingWindowRateLimiter

from extproc.example.litellm_gateway import gateway_config


class QuotaDecision(NamedTuple):
    allowed: bool
    status: int  # 0 when allowed, else 401 / 402 / 429
    reason: str


_ALLOW = QuotaDecision(True, 0, "")

def key_hash(api_key: str) -> str:
    """SHA-256 of a virtual key, used to build every Redis key name.

    Keys are credentials, so they are never used as Redis key names
    directly. `seed_keys.py` duplicates this one line so it can run
    standalone; the two must stay identical or seeded keys will not be
    found.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


# Windows for keys that set none of their own: 30 days for the key-level
# budget, 1 day for a per-model budget.
_DEFAULT_WINDOW_SECONDS = 30 * 86400
_DEFAULT_MODEL_PERIOD_SECONDS = 86400

# Everything below reads fields that seed_keys.py already validated and
# normalized: durations are whole seconds, `models` is a JSON array, and
# `expires` is a timezone-aware UTC timestamp. Nothing here re-parses units
# or tolerates a second encoding, so a value that is somehow malformed
# raises and check() fails closed rather than quietly ignoring a limit.


def _window_id(seconds: int) -> int:
    """Bucket number of the current fixed window of the given length."""
    return int(time.time()) // seconds


def _window(cfg: dict[str, str]) -> int:
    """Length of this key's budget window, in seconds."""
    raw = cfg.get("budget_duration")
    return int(raw) if raw is not None else _DEFAULT_WINDOW_SECONDS


def _parse_list(raw: str) -> list[str]:
    """The key's model allowlist, empty when the key sets none."""
    return json.loads(raw) if raw else []


def _parse_model_budgets(raw: str) -> dict[str, dict[str, Any]]:
    """The key's per-model budgets, empty when the key sets none."""
    return json.loads(raw) if raw else {}


def _model_allowed(model: str, allowed: list[str]) -> bool:
    """True if model matches an entry exactly or a `<prefix>/*` wildcard."""
    for entry in allowed:
        if entry == model:
            return True
        if entry.endswith("/*") and model.startswith(entry[:-1]):
            return True
    return False


def _expired(expires: str) -> bool:
    """True if the key's expiry has passed.

    seed_keys.py stores this as a timezone-aware UTC timestamp, so there is
    no offset to infer here.
    """
    return datetime.fromisoformat(expires) <= datetime.now(timezone.utc)


def _limit(cfg: dict[str, str], field: str) -> int | None:
    """Numeric limit for `field`, or None when the key sets no limit.

    An absent field means unlimited, but an explicit 0 means zero allowed.
    """
    raw = cfg.get(field)
    if raw is None or raw == "":
        return None
    return int(raw)


class Quota:
    """Token-budget and rate-limit enforcement against Redis.

    A Quota with no client is a working no-op rather than a special case:
    check() allows, record() does nothing. That is the shape a deployment
    without REDIS_HOST gets, so the callout never branches on whether
    quota is configured.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        settings: Optional["gateway_config.QuotaSettings"] = None,
        rate_limiter: Optional[MovingWindowRateLimiter] = None,
    ) -> None:
        self._client = client
        # Per-minute limits come from `limits`, which does the counting
        # server-side. A moving window rather than a fixed one,
        # so a client cannot send 2x the limit by straddling a minute
        # boundary. from_env() backs it with the same Redis instance;
        # tests pass an in-memory one.
        self._rates = rate_limiter or MovingWindowRateLimiter(MemoryStorage())
        self._fail_open = settings.fail_open if settings else False
        self._allow_unauthenticated = (
            settings.allow_unauthenticated if settings else False)

    @classmethod
    def from_env(
        cls,
        settings: Optional["gateway_config.QuotaSettings"] = None,
    ) -> "Quota":
        """Connect using REDIS_*. Stays inert (no client) without REDIS_HOST.

        Env vars win over the config file, so a deployment can flip either
        safety switch without editing the mounted config.
        """
        host = os.getenv("REDIS_HOST", "")
        if not host:
            return cls(settings=settings)
        fail_open = settings.fail_open if settings else False
        allow_anon = settings.allow_unauthenticated if settings else False
        # Parsed the same way as QUOTA_ALLOW_UNAUTHENTICATED: only the
        # literal "true" enables it. `!= "false"` would read a typo like
        # "0" or "no" as enabling fail-open, a typo failing toward the
        # unsafe side of a security switch.
        fail_open = os.getenv(
            "QUOTA_FAIL_OPEN",
            "true" if fail_open else "false").lower() == "true"
        allow_anon = os.getenv(
            "QUOTA_ALLOW_UNAUTHENTICATED",
            "true" if allow_anon else "false").lower() == "true"
        port = int(os.getenv("REDIS_PORT", "6379"))
        # AUTH string for the Memorystore instance, when auth is enabled.
        password = os.getenv("REDIS_AUTH_STRING") or None
        use_tls = os.getenv("REDIS_TLS", "").lower() == "true"
        client = redis.Redis(
            host=host, port=port, password=password, decode_responses=True,
            socket_timeout=2, ssl=use_tls, ssl_cert_reqs=None)
        # `limits` opens its own connection, so it takes the same details
        # in URI form. rediss:// is the TLS scheme.
        scheme = "async+rediss" if use_tls else "async+redis"
        auth = f":{password}@" if password else ""
        # Memorystore presents a certificate from a private CA that the
        # container has no root for, so verification is disabled here just
        # as it is on the client above. The connection is still encrypted.
        options = {"ssl_cert_reqs": "none"} if use_tls else {}
        storage = RedisStorage(
            f"{scheme}://{auth}{host}:{port}", implementation="redispy",
            **options)
        logging.info(
            "Quota enabled via Redis at %s:%d "
            "(fail_open=%s, allow_unauthenticated=%s)",
            host, port, fail_open, allow_anon)
        return cls(
            rate_limiter=MovingWindowRateLimiter(storage),
            client=client,
            settings=gateway_config.QuotaSettings(
                fail_open=fail_open, allow_unauthenticated=allow_anon))

    def enabled(self) -> bool:
        """True when a Redis client is installed."""
        return self._client is not None

    def unavailable(self) -> QuotaDecision:
        """The decision when the backend cannot be consulted at all.

        Honors fail_open, so the caller can use it for failures that happen
        outside check()'s own try/except, e.g. the shared config read or
        the sync-to-async bridge, without inverting the operator's choice.
        """
        if self._fail_open:
            return _ALLOW
        return QuotaDecision(False, 503, "quota backend unavailable")

    async def key_config(self, api_key: str) -> dict[str, str]:
        """Read a key's stored config, or {} when there is none.
        """
        if self._client is None or not api_key:
            return {}
        return await self._client.hgetall(f"key:{key_hash(api_key)}")

    async def _incr_with_ttl(
        self, key: str, amount: int, ttl: int
    ) -> int:
        """Add to a window counter and refresh its expiry in one round trip,
        returning the new total.

        The expiry is refreshed on every write rather than only on the first.
        The key name already carries the window id, so an over-long TTL only
        delays cleanup of a counter nothing reads again. In exchange it removes
        the window in which a crash between the increment and the expiry would
        leave a counter that never expires.
        """
        pipe = self._client.pipeline(transaction=False)
        pipe.incrby(key, amount)
        pipe.expire(key, ttl)
        return int((await pipe.execute())[0])

    async def check(
        self,
        api_key: str,
        model: str,
        cfg: Optional[dict[str, str]] = None,
    ) -> QuotaDecision:
        """Request-leg pre-check.

        Covers unknown or expired key, model allowlist, RPM, TPM, the
        accumulated token budget, and per-model budget (model_max_budget).

        With quota enabled, a request presenting no virtual key is rejected with
        401. Enforcement cannot be per request: if unauthenticated requests were
        allowed through, a caller that exhausted its budget could keep going by
        dropping the Authorization header. Deployments that genuinely want
        unauthenticated traffic can set `quota_allow_unauthenticated`, which is
        off by default.

        The TPM check gates on tokens already recorded for the current minute
        (via record()), since this request's own token usage is unknown until
        the response leg completes; matches the pre-check semantics of the
        token budget check below.

        The per-model budget check gates on spend already recorded for the
        requested model in its own window (via record(), keyed by
        `spend:<api_key>:<model>:<window_id>`), independent of the key-level
        budget window.

        A `soft_budget` below `token_budget` is warn-only: once spend reaches
        it, check() logs a warning but still allows the request.

        For every limit field, an absent field means unlimited and an explicit
        0 means zero allowed. Setting `rpm_limit: 0` shuts a key off rather
        than removing its limits.

        `fail_open` does not apply to any decision made here. It governs only
        the case where Redis itself is unreachable, below. An unknown or
        expired key is an authoritative answer from a healthy backend, and
        admitting those would restore exactly the bypass this check exists to
        prevent.

        Returns status 401 (missing, unknown, or expired key), 403 (model not
        allowed for key), 429 (rpm or tpm exceeded), or 402 (token budget or
        model budget exceeded) when denied.
        """
        if self._client is None:
            return _ALLOW
        if not api_key:
            if self._allow_unauthenticated:
                return _ALLOW
            return QuotaDecision(False, 401, "missing virtual key")
        try:
            kh = key_hash(api_key)
            if cfg is None:
                cfg = await self.key_config(api_key)
            if not cfg:
                return QuotaDecision(False, 401, "unknown key")
            expires = cfg.get("expires", "")
            if expires and _expired(expires):
                return QuotaDecision(False, 401, "key expired")
            allowed_models = _parse_list(cfg.get("models", ""))
            if allowed_models and not _model_allowed(model, allowed_models):
                return QuotaDecision(False, 403, "model not allowed for key")
            rpm_limit = _limit(cfg, "rpm_limit")
            if rpm_limit is not None:
                if not await self._rates.hit(
                        RateLimitItemPerMinute(rpm_limit), kh, "rpm"):
                    return QuotaDecision(False, 429, "rpm exceeded")
            tpm_limit = _limit(cfg, "tpm_limit")
            if tpm_limit is not None:
                # Tokens are only known once the response arrives, so this
                # gates on what record() already charged this window.
                minute = int(time.time()) // 60
                used = int(await self._client.get(f"tpm:{kh}:{minute}") or 0)
                if used >= tpm_limit:
                    return QuotaDecision(False, 429, "tpm exceeded")
            budget = _limit(cfg, "token_budget")
            soft = _limit(cfg, "soft_budget")
            if budget is not None or soft is not None:
                spend = int(await self._client.get(
                    f"spend:{kh}:{_window_id(_window(cfg))}") or 0)
                if budget is not None and spend >= budget:
                    return QuotaDecision(False, 402, "token budget exceeded")
                if soft is not None and spend >= soft:
                    logging.warning(
                        "Key %s over soft budget (%d >= %d)",
                        kh[:16], spend, soft)
            model_budget = _parse_model_budgets(
                cfg.get("model_max_budget", "")).get(model)
            if model_budget:
                limit = model_budget.get("budget_limit")
                period = int(model_budget.get("time_period")
                             or _DEFAULT_MODEL_PERIOD_SECONDS)
                if limit is not None:
                    limit = int(limit)
                    spent = int(await self._client.get(
                        f"spend:{kh}:{model}:{_window_id(period)}") or 0)
                    if spent >= limit:
                        return QuotaDecision(
                            False, 402, "model budget exceeded")
            return _ALLOW
        except Exception:
            logging.exception("Quota check failed")
            return self.unavailable()

    async def record(
        self,
        api_key: str,
        model: str,
        total_tokens: int,
        cfg: Optional[dict[str, str]] = None,
    ) -> None:
        """Response-leg update: add token usage to spend and TPM counters, plus
        the per-model spend counter when the key has a model_max_budget entry
        for this model."""
        if self._client is None or not api_key or total_tokens <= 0:
            return
        try:
            kh = key_hash(api_key)
            if cfg is None:
                cfg = await self.key_config(api_key)
            window = _window(cfg) if cfg else _DEFAULT_WINDOW_SECONDS
            await self._incr_with_ttl(
                f"spend:{kh}:{_window_id(window)}", total_tokens, window)
            model_budget = _parse_model_budgets(
                cfg.get("model_max_budget", "") if cfg else "").get(model)
            if model_budget:
                period = int(model_budget.get("time_period")
                             or _DEFAULT_MODEL_PERIOD_SECONDS)
                await self._incr_with_ttl(
                    f"spend:{kh}:{model}:{_window_id(period)}", total_tokens,
                    period)
            minute = int(time.time()) // 60
            await self._incr_with_ttl(f"tpm:{kh}:{minute}", total_tokens, 60)
        except Exception:
            logging.exception("Quota record failed")

    async def usage_headers(
        self,
        api_key: str,
        cfg: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """LiteLLM-style usage response headers for a key; {} when unavailable.
        """
        if self._client is None or not api_key:
            return {}
        try:
            kh = key_hash(api_key)
            if cfg is None:
                cfg = await self.key_config(api_key)
            if not cfg:
                return {}
            headers: dict[str, str] = {}
            spend = int(await self._client.get(
                f"spend:{kh}:{_window_id(_window(cfg))}") or 0)
            headers["x-litellm-key-spend"] = str(spend)
            budget = _limit(cfg, "token_budget")
            if budget is not None:
                headers["x-ratelimit-remaining-tokens"] = str(
                    max(0, budget - spend))
            rpm_limit = _limit(cfg, "rpm_limit")
            if rpm_limit is not None:
                stats = await self._rates.get_window_stats(
                    RateLimitItemPerMinute(rpm_limit), kh, "rpm")
                headers["x-ratelimit-remaining-requests"] = str(
                    max(0, stats.remaining))
            return headers
        except Exception:
            logging.exception("usage_headers failed")
            return {}
