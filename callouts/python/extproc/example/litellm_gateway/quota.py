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

Each `key:<api_key>` Redis hash may carry: `token_budget`, `budget_duration`,
`rpm_limit`, `tpm_limit`, `models` (JSON list or comma-separated string),
`model_max_budget` (JSON dict), `expires` (ISO-8601), `soft_budget`.

`model_max_budget` maps a model name to `{"budget_limit": <tokens>,
"time_period": <window>}` (LiteLLM's /key/generate parameter shape). Spend
against each entry is tracked separately from the key-level budget, in
`spend:<api_key>:<model>:<window_id>` keys written by record().

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

import redis

from extproc.example.litellm_gateway import gateway_config


class QuotaDecision(NamedTuple):
    allowed: bool
    status: int  # 0 when allowed, else 401 / 402 / 429
    reason: str


_ALLOW = QuotaDecision(True, 0, "")

_client: Optional[Any] = None
_enabled: bool = False
_fail_open: bool = True


def init_client() -> None:
    """Connect to Redis once. No-op without REDIS_HOST."""
    global _client, _enabled, _fail_open
    if _enabled:
        return
    host = os.getenv("REDIS_HOST", "")
    if not host:
        return
    port = int(os.getenv("REDIS_PORT", "6379"))
    default = "true" if gateway_config.quota_settings().fail_open else "false"
    _fail_open = os.getenv("QUOTA_FAIL_OPEN", default).lower() != "false"
    _set_client(redis.Redis(
        host=host, port=port, decode_responses=True, socket_timeout=2))
    logging.info(
        "Quota enabled via Redis at %s:%d (fail_open=%s)",
        host, port, _fail_open)


def _set_client(client: Any) -> None:
    """Install a Redis client and mark enabled. Also a test hook."""
    global _client, _enabled
    _client = client
    _enabled = True


def _reset() -> None:
    """Test hook: disable and drop the client."""
    global _client, _enabled, _fail_open
    _client = None
    _enabled = False
    _fail_open = True


def enabled() -> bool:
    """Return True if the quota module is active (Redis connected)."""
    return _enabled


def _window_seconds(window: str) -> int:
    if window.endswith("mo"):
        return int(window[:-2]) * 30 * 86400
    unit = window[-1]
    qty = int(window[:-1])
    return qty * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _window_id(window: str) -> int:
    return int(time.time()) // _window_seconds(window)


def _parse_list(raw: str) -> list[str]:
    """Parse a JSON list or a comma-separated string."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(v) for v in value]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_model_budgets(raw: str) -> dict[str, dict[str, Any]]:
    """Parse the model_max_budget JSON field; {} on absence or bad JSON.

    Entries whose value is not itself a dict are dropped, so a malformed
    entry means "no per-model budget for that model" rather than an
    exception later in check() or record().
    """
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            return {}
        return {k: v for k, v in value.items() if isinstance(v, dict)}
    except json.JSONDecodeError:
        return {}


def _model_allowed(model: str, allowed: list[str]) -> bool:
    """True if model matches an entry exactly or a `<prefix>/*` wildcard."""
    for entry in allowed:
        if entry == model:
            return True
        if entry.endswith("/*") and model.startswith(entry[:-1]):
            return True
    return False


def _expired(expires: str) -> bool:
    """True if the ISO-8601 expires timestamp is in the past."""
    parsed = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)


def check(api_key: str, model: str) -> QuotaDecision:
    """Request-leg pre-check: unknown/expired key, model allowlist, RPM, TPM,
    accumulated token budget, and per-model budget (model_max_budget).

    Quota is opt-in per request: a request that presents no virtual key (no
    Authorization Bearer token) is allowed through unmetered. Budgets and rate
    limits apply only to requests that present a key, so enabling quota does
    not break clients that do not use virtual keys.

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

    Returns status 401 (unknown or expired key), 403 (model not allowed for
    key), 429 (rpm or tpm exceeded), or 402 (token budget or model budget
    exceeded) when denied.
    """
    if not _enabled or not api_key:
        return _ALLOW
    try:
        cfg = _client.hgetall(f"key:{api_key}")
        if not cfg:
            return QuotaDecision(False, 401, "unknown key")
        expires = cfg.get("expires", "")
        if expires and _expired(expires):
            return QuotaDecision(False, 401, "key expired")
        allowed_models = _parse_list(cfg.get("models", ""))
        if allowed_models and not _model_allowed(model, allowed_models):
            return QuotaDecision(False, 403, "model not allowed for key")
        rpm_limit = int(cfg.get("rpm_limit", 0) or 0)
        if rpm_limit:
            minute = int(time.time()) // 60
            rkey = f"rpm:{api_key}:{minute}"
            count = _client.incr(rkey)
            if count == 1:
                _client.expire(rkey, 60)
            if count > rpm_limit:
                return QuotaDecision(False, 429, "rpm exceeded")
        tpm_limit = int(cfg.get("tpm_limit", 0) or 0)
        if tpm_limit:
            minute = int(time.time()) // 60
            used = int(_client.get(f"tpm:{api_key}:{minute}") or 0)
            if used >= tpm_limit:
                return QuotaDecision(False, 429, "tpm exceeded")
        budget = int(cfg.get("token_budget", 0) or 0)
        soft = int(cfg.get("soft_budget", 0) or 0)
        if budget or soft:
            window = cfg.get("budget_duration", "30d")
            spend = int(_client.get(
                f"spend:{api_key}:{_window_id(window)}") or 0)
            if budget and spend >= budget:
                return QuotaDecision(False, 402, "token budget exceeded")
            if soft and spend >= soft:
                key_hash = hashlib.sha256(
                    api_key.encode("utf-8")).hexdigest()[:16]
                logging.warning(
                    "Key %s over soft budget (%d >= %d)",
                    key_hash, spend, soft)
        model_budget = _parse_model_budgets(
            cfg.get("model_max_budget", "")).get(model)
        if model_budget:
            limit = int(model_budget.get("budget_limit", 0) or 0)
            period = str(model_budget.get("time_period", "1d"))
            if limit:
                spent = int(_client.get(
                    f"spend:{api_key}:{model}:{_window_id(period)}") or 0)
                if spent >= limit:
                    return QuotaDecision(
                        False, 402, "model budget exceeded")
        return _ALLOW
    except Exception:
        logging.exception("Quota check failed")
        return _ALLOW if _fail_open else QuotaDecision(
            False, 503, "quota backend unavailable")


def record(api_key: str, model: str, total_tokens: int) -> None:
    """Response-leg update: add token usage to spend and TPM counters, plus
    the per-model spend counter when the key has a model_max_budget entry
    for this model."""
    if not _enabled or not api_key or total_tokens <= 0:
        return
    try:
        cfg = _client.hgetall(f"key:{api_key}")
        window = cfg.get("budget_duration", "30d") if cfg else "30d"
        skey = f"spend:{api_key}:{_window_id(window)}"
        if _client.incrby(skey, total_tokens) == total_tokens:
            _client.expire(skey, _window_seconds(window))
        model_budget = _parse_model_budgets(
            cfg.get("model_max_budget", "") if cfg else "").get(model)
        if model_budget:
            period = str(model_budget.get("time_period", "1d"))
            mkey = f"spend:{api_key}:{model}:{_window_id(period)}"
            if _client.incrby(mkey, total_tokens) == total_tokens:
                _client.expire(mkey, _window_seconds(period))
        minute = int(time.time()) // 60
        tkey = f"tpm:{api_key}:{minute}"
        if _client.incrby(tkey, total_tokens) == total_tokens:
            _client.expire(tkey, 60)
    except Exception:
        logging.exception("Quota record failed")


def usage_headers(api_key: str) -> dict[str, str]:
    """LiteLLM-style usage response headers for a key; {} when unavailable.
    """
    if not _enabled or not api_key:
        return {}
    try:
        cfg = _client.hgetall(f"key:{api_key}")
        if not cfg:
            return {}
        headers: dict[str, str] = {}
        window = cfg.get("budget_duration", "30d")
        spend = int(_client.get(
            f"spend:{api_key}:{_window_id(window)}") or 0)
        headers["x-litellm-key-spend"] = str(spend)
        budget = int(cfg.get("token_budget", 0) or 0)
        if budget:
            headers["x-ratelimit-remaining-tokens"] = str(
                max(0, budget - spend))
        rpm_limit = int(cfg.get("rpm_limit", 0) or 0)
        if rpm_limit:
            minute = int(time.time()) // 60
            used = int(_client.get(f"rpm:{api_key}:{minute}") or 0)
            headers["x-ratelimit-remaining-requests"] = str(
                max(0, rpm_limit - used))
        return headers
    except Exception:
        logging.exception("usage_headers failed")
        return {}
