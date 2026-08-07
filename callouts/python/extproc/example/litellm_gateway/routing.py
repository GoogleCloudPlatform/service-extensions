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

# Records which strategies rewrote the model, set by the route
# extension and read by the traffic extension for the request span.
STRATEGY_HEADER = "x-litellm-routing-strategy"

# Provider prefixes the URL map routes on.
PROVIDER_PREFIXES: tuple[str, ...] = (
    "vertex_ai/", "anthropic/", "groq/", "openrouter/")

class Router:
    """The routing strategies and the four tables that drive them.

    Routing ships DISABLED: a Router built with no settings has empty
    tables and leaves every request unchanged, so the callout behaves as
    the plain translation gateway. The feature flag is the
    `router_settings` section of a GATEWAY_CONFIG file (config.example.yaml
    has a working demo table), which the caller parses and hands in here. A
    strategy is active exactly when its table is non-empty.

    All four tables are keyed off the routing header:

      model_group_alias  friendly name -> full LiteLLM model id, resolved
                         before the URL map routes (the URL map alone can
                         only prefix-match)
      tag_rules          (provider prefix, tag value) -> model id, e.g. a
                         premium tag upgrading Vertex flash to pro
      weighted_groups    header value -> [(member, weight)], an A/B split
                         across a model group
      shuffle_groups     header value -> [members], one picked at random
                         per request (simple-shuffle)
    """

    def __init__(
        self,
        settings: Optional["gateway_config.RoutingSettings"] = None,
    ) -> None:
        self._aliases: dict[str, str] = (
            dict(settings.model_group_alias) if settings else {})
        self._tag_rules: dict[tuple[str, str], str] = (
            dict(settings.tag_rules) if settings else {})
        self._weighted: dict[str, list[tuple[str, int]]] = (
            dict(settings.weighted_groups) if settings else {})
        self._shuffle: dict[str, list[str]] = (
            dict(settings.shuffle_groups) if settings else {})

    def enabled(self) -> bool:
        """True when any routing strategy is active (feature flag is on).

        The traffic extension consults this before letting the x-model-id
        header override the request body's model, so a deployment without
        router_settings keeps the original body-driven behavior exactly.
        """
        return bool(
            self._aliases or self._tag_rules or self._weighted
            or self._shuffle)

    # The strategies below run in the order listed in compute_route(). Each
    # sees the routing header as left by the previous one, so aliases
    # resolve before tag upgrades, and so on. A strategy with an empty table
    # returns no rewrite, which is how a disabled strategy stays inert.

    def model_alias_route(self, headers: dict[str, str]) -> dict[str, str]:
        """Resolve a friendly alias in the routing header to a full model id."""
        model_id = headers.get(ROUTING_HEADER, "")
        target = self._aliases.get(model_id)
        if target and target != model_id:
            return {ROUTING_HEADER: target}
        return {}

    def tag_based_route(self, headers: dict[str, str]) -> dict[str, str]:
        """Route by a tag header (x-tier) within the request's provider."""
        model_id = headers.get(ROUTING_HEADER, "")
        tag = headers.get("x-tier", "").lower()
        if not tag:
            return {}
        for prefix in PROVIDER_PREFIXES:
            if model_id.startswith(prefix):
                target = self._tag_rules.get((prefix, tag))
                if target and target != model_id:
                    return {ROUTING_HEADER: target}
                break
        return {}

    def weighted_split_route(
        self,
        headers: dict[str, str],
        hash_header: str = "x-request-id",
    ) -> dict[str, str]:
        """A/B / weighted split across a model group, by a stable header hash.

        When the request carries hash_header (default x-request-id), the
        member is chosen by hashing it, so the same id always lands on the
        same member and a client retrying a request keeps its assignment.
        """
        model_id = headers.get(ROUTING_HEADER, "")
        members = self._weighted.get(model_id)
        if not members:
            return {}
        total = sum(weight for _, weight in members)
        if total <= 0:
            return {}
        key = headers.get(hash_header)
        bucket = (
            int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % total
            if key else random.randrange(total))
        cumulative = 0
        for member, weight in members:
            cumulative += weight
            if bucket < cumulative:
                return {ROUTING_HEADER: member} if member != model_id else {}
        return {}

    def simple_shuffle_route(self, headers: dict[str, str]) -> dict[str, str]:
        """Pick a random member of a model group (simple-shuffle balancing)."""
        model_id = headers.get(ROUTING_HEADER, "")
        members = self._shuffle.get(model_id)
        if not members:
            return {}
        choice = random.choice(members)
        return {ROUTING_HEADER: choice} if choice != model_id else {}

    def compute_route(self, headers: dict[str, str]) -> dict[str, str]:
        """Compose the enabled strategies into the net header rewrite.

        Returns the header changes the route extension should apply; an
        empty dict means leave routing unchanged.
        """
        original = headers.get(ROUTING_HEADER, "")
        current = dict(headers)
        fired: list[str] = []
        for strategy in (
            self.model_alias_route,
            self.tag_based_route,
            self.weighted_split_route,
            self.simple_shuffle_route,
        ):
            rewrite = strategy(current)
            if rewrite:
                current.update(rewrite)
                fired.append(strategy.__name__)
        final = current.get(ROUTING_HEADER, "")
        if final and final != original:
            # The strategy names ride along as a header because the route
            # extension and the traffic extension are separate calls: the
            # leg that picks the model is not the leg that opens the span,
            # so without this the rewrite is invisible in telemetry.
            return {
                ROUTING_HEADER: final,
                STRATEGY_HEADER: ",".join(fired),
            }
        return {}
