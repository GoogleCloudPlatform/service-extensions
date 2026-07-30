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

"""Route-extension routing strategies for the regional config.

These map to https://docs.litellm.ai/docs/routing-load-balancing. Each strategy
is independent and individually testable, so a deployment enables only the ones
it wants (an empty config map makes a strategy a no-op).

The traffic-extension callout (service_callout_example.py) treats x-model-id
(after any route-extension rewrite) as authoritative over the request body's
model field whenever it carries a known provider prefix, so a header rewrite
here changes which model is served, not just which backend receives the
request:
  * model_alias_route    : a friendly alias resolves to a full model id; the
                           traffic extension then serves that model directly.
  * tag_based_route      : a tag (e.g. tier) selects a full model id, which
                           the traffic extension serves.
  * weighted_split_route : A/B / weighted split across members of a model
                           group. The members still need to be backends able
                           to serve the model chosen for the request.
  * simple_shuffle_route : random pick across a model group, same
                           backend-capability requirement.

Strategies that need the request body (content-based routing) or live
cross-request state (least-busy, latency-based, usage-based, semantic
fallbacks, request prioritization) cannot run in a route extension and are
intentionally absent. Provider failover is also out: after the traffic
extension's transform the payload is provider-native, so the load balancer
cannot replay it at a different provider's backend. (Same-backend Envoy
retries and optional health checks exist on the regional ALB but are not
part of this sample.)

Routing is feature-flagged: the module ships with all four strategy tables
empty (disabled), and the `router_settings` section of a GATEWAY_CONFIG file
is what turns it on (configure() installs the tables; enabled() reports the
flag state). Without it, the route extension rewrites nothing and the
traffic extension never overrides the body model, so the sample behaves
exactly like the original translation-only gateway.
"""

import hashlib
import random
from typing import Optional

from extproc.example.litellm_gateway import gateway_config

# The routing header the URL map prefix-matches on, and that these strategies
# rewrite. Carries the LiteLLM model id (e.g. anthropic/claude-...).
ROUTING_HEADER = "x-model-id"

# Provider prefixes the URL map routes on.
PROVIDER_PREFIXES: tuple[str, ...] = (
    "vertex_ai/", "anthropic/", "groq/", "openrouter/")

# Routing ships DISABLED: all four strategy tables below are empty, so the
# route extension leaves every request unchanged and the callout behaves as
# the plain translation gateway. The feature flag is the `router_settings`
# section of a GATEWAY_CONFIG file (see config.example.yaml for a working
# demo table); a strategy is active exactly when its table is non-empty.

# Friendly name -> full LiteLLM model id. The client sends the alias in the
# routing header (x-model-id); the route extension resolves it before the
# URL map routes (the URL map alone can only prefix-match).
MODEL_ALIASES: dict[str, str] = {}

# (provider prefix, tag value) -> model id to route to, e.g. a premium tag
# upgrading a Vertex request from flash to pro.
TAG_RULES: dict[tuple[str, str], str] = {}

# routing-header value -> list of (member_model_id, weight): A/B / weighted
# split across a model group by a stable hash of x-request-id.
WEIGHTED_GROUPS: dict[str, list[tuple[str, int]]] = {}

# routing-header value -> list of member model ids; one is chosen at random
# per request (simple-shuffle).
SHUFFLE_GROUPS: dict[str, list[str]] = {}

# Active strategy config. Empty (disabled) until configure() installs values
# from the gateway config file.
_aliases: dict[str, str] = dict(MODEL_ALIASES)
_tag_rules: dict[tuple[str, str], str] = dict(TAG_RULES)
_weighted: dict[str, list[tuple[str, int]]] = dict(WEIGHTED_GROUPS)
_shuffle: dict[str, list[str]] = dict(SHUFFLE_GROUPS)


def configure(settings: Optional["gateway_config.RoutingSettings"]) -> None:
    """Install strategy config from the gateway config file.

    This is the routing feature flag: None (no file or no router_settings
    section) leaves routing disabled. A provided settings object replaces
    all four tables, so the config file fully defines the routing behavior.
    """
    global _aliases, _tag_rules, _weighted, _shuffle
    if settings is None:
        return
    _aliases = dict(settings.model_group_alias)
    _tag_rules = dict(settings.tag_rules)
    _weighted = dict(settings.weighted_groups)
    _shuffle = dict(settings.shuffle_groups)


def enabled() -> bool:
    """True when any routing strategy is active (feature flag is on).

    The traffic extension consults this before letting the x-model-id
    header override the request body's model, so a deployment without
    router_settings keeps the original body-driven behavior exactly.
    """
    return bool(_aliases or _tag_rules or _weighted or _shuffle)


def _reset() -> None:
    """Test hook: restore the disabled (empty-table) state."""
    global _aliases, _tag_rules, _weighted, _shuffle
    _aliases = dict(MODEL_ALIASES)
    _tag_rules = dict(TAG_RULES)
    _weighted = dict(WEIGHTED_GROUPS)
    _shuffle = dict(SHUFFLE_GROUPS)


def model_alias_route(headers: dict[str, str]) -> dict[str, str]:
    """Resolve a friendly alias in the routing header to a full model id."""
    model_id = headers.get(ROUTING_HEADER, "")
    target = _aliases.get(model_id)
    if target and target != model_id:
        return {ROUTING_HEADER: target}
    return {}


def tag_based_route(headers: dict[str, str]) -> dict[str, str]:
    """Route by a tag header (x-tier) within the request's provider."""
    model_id = headers.get(ROUTING_HEADER, "")
    tag = headers.get("x-tier", "").lower()
    if not tag:
        return {}
    for prefix in PROVIDER_PREFIXES:
        if model_id.startswith(prefix):
            target = _tag_rules.get((prefix, tag))
            if target and target != model_id:
                return {ROUTING_HEADER: target}
            break
    return {}


def weighted_split_route(
    headers: dict[str, str],
    hash_header: str = "x-request-id",
) -> dict[str, str]:
    """A/B / weighted split across a model group, by a stable header hash.

    Deterministic (hashes a stable header, falling back to the model id), so it
    needs no per-request randomness and is reproducible for a given client.
    When a request has no hash_header (the default is x-request-id, which
    most clients don't set on their own), every such request hashes to the
    same value and therefore lands on the same member: the split only varies
    across requests when clients actually send a distinct id.
    """
    model_id = headers.get(ROUTING_HEADER, "")
    members = _weighted.get(model_id)
    if not members:
        return {}
    total = sum(weight for _, weight in members)
    if total <= 0:
        return {}
    key = headers.get(hash_header) or model_id
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % total
    cumulative = 0
    for member, weight in members:
        cumulative += weight
        if bucket < cumulative:
            return {ROUTING_HEADER: member} if member != model_id else {}
    return {}


def simple_shuffle_route(headers: dict[str, str]) -> dict[str, str]:
    """Pick a random member of a model group (simple-shuffle load balancing)."""
    model_id = headers.get(ROUTING_HEADER, "")
    members = _shuffle.get(model_id)
    if not members:
        return {}
    choice = random.choice(members)
    return {ROUTING_HEADER: choice} if choice != model_id else {}


# Enabled strategies, in order. Each sees the routing header as left by the
# previous one, so aliases resolve before tag upgrades, etc. To enable or
# disable a strategy, add or remove it here (or leave its config map empty).
_STRATEGIES = (
    model_alias_route,
    tag_based_route,
    weighted_split_route,
    simple_shuffle_route,
)


def compute_route(headers: dict[str, str]) -> dict[str, str]:
    """Compose the enabled strategies into the net routing-header rewrite.

    Returns the header changes the route extension should apply; an empty dict
    means leave routing unchanged.
    """
    original = headers.get(ROUTING_HEADER, "")
    current = dict(headers)
    for strategy in _STRATEGIES:
        rewrite = strategy(current)
        if rewrite:
            current.update(rewrite)
    final = current.get(ROUTING_HEADER, "")
    if final and final != original:
        return {ROUTING_HEADER: final}
    return {}
