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

"""Unit tests for the route-extension routing strategies. Pure functions, no LB.

Each LiteLLM-named strategy is tested independently, then the composed
compute_route.
"""

import collections
import os
import random
from unittest.mock import patch


from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.litellm_gateway import gateway_config
from extproc.example.litellm_gateway import routing
from extproc.example.litellm_gateway.service_callout_example import (
    LiteLLMGatewayCallout, _state,
)


class _Ctx:
    pass


def _hdrs(d):
    hm = HeaderMap()
    for k, v in d.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.HttpHeaders(headers=hm)


def _demo_settings() -> gateway_config.RoutingSettings:
    """The demo routing table from config.example.yaml.

    Routing ships disabled (empty tables); tests that exercise a strategy
    install this table first, exactly as a deployment would via
    GATEWAY_CONFIG router_settings.
    """
    return gateway_config.RoutingSettings(
        model_group_alias={
            "fast": "vertex_ai/gemini-2.5-flash",
            "smart": "anthropic/claude-haiku-4-5",
            "cheap": "openrouter/openai/gpt-oss-20b:free",
        },
        tag_rules={("vertex_ai/", "premium"): "vertex_ai/gemini-2.5-pro"},
        weighted_groups={},
        shuffle_groups={},
    )


# --- model_alias_route -----------------------------------------------------

def test_model_alias_resolves_to_full_model_id():
    router = routing.Router(_demo_settings())
    out = router.model_alias_route({"x-model-id": "cheap"})
    assert out["x-model-id"] == "openrouter/openai/gpt-oss-20b:free"


def test_model_alias_unknown_alias_no_change():
    router = routing.Router()
    out = router.model_alias_route(
        {"x-model-id": "anthropic/claude-haiku-4-5"})
    assert out == {}


# --- tag_based_route -------------------------------------------------------

def test_tag_premium_upgrades_within_provider():
    router = routing.Router(_demo_settings())
    out = router.tag_based_route({
        "x-model-id": "vertex_ai/gemini-2.5-flash",
        "x-tier": "premium",
    })
    assert out["x-model-id"] == "vertex_ai/gemini-2.5-pro"


def test_tag_absent_no_change():
    router = routing.Router()
    out = router.tag_based_route(
        {"x-model-id": "vertex_ai/gemini-2.5-flash"})
    assert out == {}


# --- weighted_split_route --------------------------------------------------

def test_weighted_split_deterministic_by_hash():
    # "group-x" is not a default group, so a fallback to built-in defaults
    # would leave the header unchanged and fail the membership assertion.
    group = {"group-x": [
        ("model-a", 50),
        ("model-b", 50),
    ]}
    router = routing.Router(gateway_config.RoutingSettings(
        model_group_alias={}, tag_rules={}, weighted_groups=group,
        shuffle_groups={}))
    a = router.weighted_split_route(
        {"x-model-id": "group-x", "x-request-id": "req-A"})
    b = router.weighted_split_route(
        {"x-model-id": "group-x", "x-request-id": "req-A"})
    # Same hash key -> same deterministic choice.
    assert a == b
    chosen = a.get("x-model-id", "group-x")
    assert chosen in ("model-a", "model-b")


def _weighted_group(members):
    return routing.Router(gateway_config.RoutingSettings(
        model_group_alias={}, tag_rules={}, shuffle_groups={},
        weighted_groups={"group-w": members}))


def test_weighted_split_without_hash_header_honors_the_weights():
    # No x-request-id means no stable id to hash, so the bucket is drawn at
    # random. Sweep every bucket in range to prove the draw maps onto the
    # configured shares exactly: 90/10 stays 90/10.
    router = _weighted_group([("model-a", 90), ("model-b", 10)])
    counts = collections.Counter()
    for bucket in range(100):
        with patch.object(routing.random, "randrange", return_value=bucket):
            out = router.weighted_split_route({"x-model-id": "group-w"})
        counts[out.get("x-model-id", "group-w")] += 1
    assert counts == collections.Counter({"model-a": 90, "model-b": 10})


def test_weighted_split_without_hash_header_is_not_pinned_to_one_member():
    router = _weighted_group([("model-a", 50), ("model-b", 50)])
    random.seed(20260803)
    seen = {
        router.weighted_split_route(
            {"x-model-id": "group-w"})["x-model-id"]
        for _ in range(200)
    }
    assert seen == {"model-a", "model-b"}


def test_weighted_split_with_hash_header_ignores_randomness():
    # The stable-id path must not have picked up the random draw: a request
    # carrying x-request-id stays deterministic regardless of random state.
    router = _weighted_group([("model-a", 50), ("model-b", 50)])
    hdrs = {"x-model-id": "group-w", "x-request-id": "req-A"}
    with patch.object(routing.random, "randrange") as rr:
        first = router.weighted_split_route(hdrs)
        second = router.weighted_split_route(hdrs)
    rr.assert_not_called()
    assert first == second


def test_weighted_split_model_not_in_any_group_no_change():
    # A model id that is not a configured weighted-group key is unaffected.
    router = routing.Router()
    out = router.weighted_split_route(
        {"x-model-id": "anthropic/claude-haiku-4-5"})
    assert out == {}


# --- simple_shuffle_route --------------------------------------------------

def test_simple_shuffle_picks_a_member():
    # "group-x" is not a default group, so a fallback to built-in defaults
    # would leave the header unchanged and fail the membership assertion.
    group = {"group-x": ["model-a", "model-b"]}
    router = routing.Router(gateway_config.RoutingSettings(
        model_group_alias={}, tag_rules={}, weighted_groups={},
        shuffle_groups=group))
    out = router.simple_shuffle_route({"x-model-id": "group-x"})
    chosen = out.get("x-model-id", "group-x")
    assert chosen in group["group-x"]


def test_simple_shuffle_empty_group_no_change():
    router = routing.Router()
    out = router.simple_shuffle_route({"x-model-id": "groq/compound-beta"})
    assert out == {}


# --- compute_route (composition) -------------------------------------------

def test_compute_route_alias_and_tag_via_pipeline():
    # Alias resolves to a full model id; a Vertex request with a premium tag
    # upgrades flash to pro. Both routed through the composed pipeline.
    router = routing.Router(_demo_settings())
    assert router.compute_route({"x-model-id": "fast"})["x-model-id"] == (
        "vertex_ai/gemini-2.5-flash")
    assert router.compute_route({
        "x-model-id": "vertex_ai/gemini-2.5-flash", "x-tier": "premium",
    })["x-model-id"] == "vertex_ai/gemini-2.5-pro"


def test_compute_route_no_change_returns_empty():
    router = routing.Router()
    assert router.compute_route({"x-model-id": "groq/compound-beta"}) == {}


def test_compute_route_missing_header_returns_empty():
    router = routing.Router()
    assert router.compute_route({}) == {}


def test_configure_replaces_aliases():
    router = routing.Router(gateway_config.RoutingSettings(
        model_group_alias={"tiny": "groq/compound-beta"},
        tag_rules={}, weighted_groups={}, shuffle_groups={}))
    # compute_route also reports which strategy fired, so the traffic
    # extension can attribute the rewrite on the span.
    assert router.compute_route({"x-model-id": "tiny"}) == {
        "x-model-id": "groq/compound-beta",
        "x-litellm-routing-strategy": "model_alias_route"}
    # Built-in default aliases are replaced, not merged.
    assert router.compute_route({"x-model-id": "fast"}) == {}


def test_compute_route_reports_every_strategy_that_fired():
    # An alias resolving to a Vertex model that a premium tag then upgrades
    # goes through two strategies; both are named so the span shows why the
    # served model differs from the requested one.
    router = routing.Router(gateway_config.RoutingSettings(
        model_group_alias={"fast": "vertex_ai/gemini-2.5-flash"},
        tag_rules={("vertex_ai/", "premium"): "vertex_ai/gemini-2.5-pro"},
        weighted_groups={}, shuffle_groups={}))
    out = router.compute_route({"x-model-id": "fast", "x-tier": "premium"})
    assert out["x-model-id"] == "vertex_ai/gemini-2.5-pro"
    assert out["x-litellm-routing-strategy"] == (
        "model_alias_route,tag_based_route")


def test_no_rewrite_reports_no_strategy():
    router = routing.Router()
    assert router.compute_route({"x-model-id": "anthropic/claude"}) == {}


def test_configure_none_keeps_disabled():
    # No config file (or no router_settings section) means the routing
    # feature flag stays off: nothing rewrites.
    router = routing.Router(None)
    assert router.enabled() is False
    assert router.compute_route({"x-model-id": "fast"}) == {}


def test_enabled_flag_tracks_configuration():
    # The feature flag is a property of the Router that was built, so a
    # configured and an unconfigured one can coexist.
    assert routing.Router().enabled() is False
    assert routing.Router(_demo_settings()).enabled() is True


def test_provider_prefixes_public():
    assert "vertex_ai/" in routing.PROVIDER_PREFIXES


def test_route_mode_without_a_rewrite_leaves_the_route_cache_alone():
    # The route extension matches every path the gateway serves, including
    # ones carrying no routable model id and models that hit no
    # alias or tag rule. Those requests must not force the URL map to
    # re-resolve a backend that is not going to change.
    with patch.dict(os.environ, {
        "GCP_PROJECT_ID": "p", "GCP_REGION": "us-central1"
    }):
        svc = LiteLLMGatewayCallout(
            disable_tls=True, plaintext_address=("0.0.0.0", 0))
    try:
        svc.router = routing.Router(_demo_settings())
        ctx = _Ctx()
        _state(ctx).route_mode = True
        out = svc.on_request_headers(
            _hdrs({":path": "/v1/embeddings", ":method": "POST"}), ctx)
        cr = out.request_headers.response
        assert cr.clear_route_cache is False
        assert list(cr.header_mutation.set_headers) == []
        # With no rewrite, nothing would overwrite the strategy header,
        # so the extension strips it; a client cannot forge attribution.
        assert routing.STRATEGY_HEADER in list(
            cr.header_mutation.remove_headers)
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()


def test_route_mode_rewrites_and_recomputes():
    with patch.dict(os.environ, {
        "GCP_PROJECT_ID": "p", "GCP_REGION": "us-central1"
    }):
        svc = LiteLLMGatewayCallout(
            disable_tls=True, plaintext_address=("0.0.0.0", 0))
    try:
        # Turn the routing feature flag on, as a GATEWAY_CONFIG file would.
        svc.router = routing.Router(_demo_settings())
        ctx = _Ctx()
        _state(ctx).route_mode = True
        out = svc.on_request_headers(
            _hdrs({
                ":path": "/v1/chat/completions",
                ":method": "POST",
                "x-model-id": "vertex_ai/gemini-2.5-flash",
                "x-tier": "premium",
            }),
            ctx,
        )
        cr = out.request_headers.response
        assert cr.clear_route_cache is True
        rewritten = {
            h.header.key: h.header.raw_value.decode()
            for h in cr.header_mutation.set_headers
        }
        assert rewritten["x-model-id"] == "vertex_ai/gemini-2.5-pro"
        assert _state(ctx).is_llm is False
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()
