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

"""Unit tests for the OpenTelemetry helper. In-memory exporter, no network."""

import json
import os
from unittest.mock import patch

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.litellm_gateway import gateway_config, telemetry
from extproc.example.litellm_gateway.service_callout_example import (
    LiteLLMGatewayCallout, _ProviderRequest,
)


@pytest.fixture
def exporter():
    """An in-memory exporter. Returns (exporter, provider) so a test can
    build a Telemetry around it with whatever settings it needs."""
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    return exp, provider


class _Ctx:
    pass


def _telemetry(exporter, redact=True):
    """Telemetry wired to the in-memory exporter."""
    _, provider = exporter
    return telemetry.Telemetry.from_provider(
        provider,
        gateway_config.TelemetrySettings(redact_user_api_key_info=redact))


def _spans(exporter):
    return exporter[0].get_finished_spans()


def _hdrs(d):
    hm = HeaderMap()
    for k, v in d.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.HttpHeaders(headers=hm)


@pytest.fixture
def metrics_reader():
    """An in-memory meter, wired with the same views production uses."""
    reader = InMemoryMetricReader()
    return reader, MeterProvider(
        metric_readers=[reader], views=telemetry._METRIC_VIEWS)


def _points(reader, name):
    """Every data point recorded for a metric, with its attributes."""
    out = []
    data = reader.get_metrics_data()
    for rm in (data.resource_metrics if data else []):
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == name:
                    out.extend(m.data.data_points)
    return out


def test_genai_metrics_recorded(exporter, metrics_reader):
    # The spec names two client metrics; both must carry the operation,
    # provider and model so a dashboard can break usage down by them.
    reader, meter_provider = metrics_reader
    _, provider = exporter
    tel = telemetry.Telemetry.from_provider(
        provider, meter_provider=meter_provider)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=9, completion_tokens=16, total_tokens=25,
        status=200, streaming=False, operation="chat", duration_s=1.5)

    tokens = _points(reader, "gen_ai.client.token.usage")
    by_type = {p.attributes["gen_ai.token.type"]: p for p in tokens}
    assert set(by_type) == {"input", "output"}
    assert by_type["input"].sum == 9
    assert by_type["output"].sum == 16
    assert by_type["input"].attributes["gen_ai.provider.name"] == "anthropic"
    assert by_type["input"].attributes["gen_ai.operation.name"] == "chat"

    dur = _points(reader, "gen_ai.client.operation.duration")
    assert len(dur) == 1 and dur[0].sum == 1.5
    assert "error.type" not in dur[0].attributes


def test_metrics_use_the_spec_bucket_boundaries(exporter, metrics_reader):
    # Without the Views the SDK would use its default duration buckets,
    # which are wrong for token counts spanning several orders of magnitude.
    reader, meter_provider = metrics_reader
    _, provider = exporter
    tel = telemetry.Telemetry.from_provider(
        provider, meter_provider=meter_provider)
    tel.end_request_span(
        None, provider="anthropic", model="m", prompt_tokens=1,
        completion_tokens=1, total_tokens=2, status=200, streaming=False,
        duration_s=0.5)
    assert list(_points(reader, "gen_ai.client.token.usage")[0]
                .explicit_bounds) == telemetry._TOKEN_BUCKETS
    assert list(_points(reader, "gen_ai.client.operation.duration")[0]
                .explicit_bounds) == telemetry._DURATION_BUCKETS


def test_failed_operation_records_error_type(exporter, metrics_reader):
    reader, meter_provider = metrics_reader
    _, provider = exporter
    tel = telemetry.Telemetry.from_provider(
        provider, meter_provider=meter_provider)
    tel.end_request_span(
        None, provider="anthropic", model="m", prompt_tokens=None,
        completion_tokens=None, total_tokens=None, status=429,
        streaming=False, duration_s=0.2)
    dur = _points(reader, "gen_ai.client.operation.duration")[0]
    assert dur.attributes["error.type"] == "429"


def test_metrics_are_inert_without_a_meter(exporter):
    # Tracing on, metrics off: recording must not raise.
    _, provider = exporter
    tel = telemetry.Telemetry.from_provider(provider)
    tel.end_request_span(
        None, provider="anthropic", model="m", prompt_tokens=1,
        completion_tokens=1, total_tokens=2, status=200, streaming=False,
        duration_s=0.1)


def test_span_carries_genai_attributes(exporter):
    tel = _telemetry(exporter)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=10, completion_tokens=5, total_tokens=15,
        status=200, streaming=False)
    spans = _spans(exporter)
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["gen_ai.provider.name"] == "anthropic"
    assert attrs["gen_ai.request.model"] == "claude-haiku-4-5"
    assert attrs["litellm.usage.total_tokens"] == 15
    assert attrs["http.response.status_code"] == 200


def test_new_span_attributes(exporter):
    # Redaction is on by default, so opt out to see the key hash.
    tel = _telemetry(exporter, redact=False)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=9, completion_tokens=16, total_tokens=25,
        status=200, streaming=True, operation="chat",
        api_key="vk-secret", call_id="call-123")
    exported = _spans(exporter)[0]
    attrs = exported.attributes
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["litellm.call_id"] == "call-123"
    assert attrs["llm.is_streaming"] is True
    assert "llm.streaming" not in attrs
    key_hash = attrs["user_api_key_hash"]
    assert len(key_hash) == 16 and "vk-secret" not in key_hash
    # Known Anthropic model: cost should resolve to a positive float.
    assert attrs["litellm.cost.total_cost"] > 0


def test_span_named_per_genai_spec(exporter):
    # GenAI semconv wants "{operation} {model}", not a fixed span name.
    tel = _telemetry(exporter)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        status=200, streaming=False, operation="chat")
    assert _spans(exporter)[0].name == "chat claude-haiku-4-5"


def test_rejected_span_does_not_keep_the_placeholder_name(exporter):
    # A quota or bad-body rejection ends the span before any model is
    # known. Exactly that denied traffic must not keep the "llm.request"
    # placeholder the span was opened with; it gets the operation alone.
    tel = _telemetry(exporter)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="", model="", prompt_tokens=None,
        completion_tokens=None, total_tokens=None,
        status=401, streaming=False, operation="chat")
    assert _spans(exporter)[0].name == "chat"


def test_rewritten_model_records_original_and_strategy(exporter):
    # A routing strategy changed the served model, so the span has to show
    # what the client asked for and what changed it.
    tel = _telemetry(exporter)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="vertex_ai", model="gemini-2.5-pro",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        status=200, streaming=False, operation="chat",
        requested_model="vertex_ai/gemini-2.5-flash",
        routing_strategy="tag_based_route")
    attrs = _spans(exporter)[0].attributes
    assert attrs["litellm.request.original_model"] == (
        "vertex_ai/gemini-2.5-flash")
    assert attrs["litellm.routing_strategy"] == "tag_based_route"


def test_unrouted_request_omits_the_original_model(exporter):
    # The caller passes requested_model only when a rewrite served a
    # different model (comparing full LiteLLM ids in _original_model);
    # empty means unrouted and the attribute is omitted.
    tel = _telemetry(exporter)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        status=200, streaming=False,
        requested_model="")
    attrs = _spans(exporter)[0].attributes
    assert "litellm.request.original_model" not in attrs


def test_redact_key_info(exporter):
    tel = _telemetry(exporter, redact=True)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        status=200, streaming=False, api_key="vk-secret")
    attrs = _spans(exporter)[0].attributes
    assert "user_api_key_hash" not in attrs


def test_unknown_model_omits_cost(exporter):
    tel = _telemetry(exporter)
    span = tel.start_request_span({})
    tel.end_request_span(
        span, provider="nope", model="not-a-real-model",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        status=200, streaming=False)
    attrs = _spans(exporter)[0].attributes
    assert "litellm.cost.total_cost" not in attrs


def test_inert_when_disabled():
    # A Telemetry with no tracer is a working no-op, not a special case.
    tel = telemetry.Telemetry()
    assert tel.enabled() is False
    assert tel.start_request_span({}) is None
    # Must not raise on a None span.
    tel.end_request_span(
        None, provider="x", model="y", prompt_tokens=None,
        completion_tokens=None, total_tokens=None, status=200, streaming=False)


def test_span_emitted_for_full_request(exporter):
    with patch.dict(
            os.environ,
            {"GCP_PROJECT_ID": "p", "GCP_REGION": "us-central1"}):
        svc = LiteLLMGatewayCallout(
            disable_tls=True, plaintext_address=("0.0.0.0", 0))
    try:
        # Point the callout at the in-memory exporter. No global provider to
        # install and nothing to unwind afterwards.
        svc.telemetry = _telemetry(exporter)
        ctx = _Ctx()
        svc.on_request_headers(
            _hdrs({":path": "/v1/chat/completions",
                   ":method": "POST"}), ctx)
        pr = _ProviderRequest(
            api_base_url="https://api.anthropic.com/v1/messages",
            headers={"x-api-key": "k"},
            body={"x": 1}, provider="anthropic",
            model="claude-haiku-4-5")
        with patch.object(svc, "_build_provider_request", return_value=pr):
            svc.on_request_body(
                service_pb2.HttpBody(
                    body=json.dumps(
                        {"model": "anthropic/claude-haiku-4-5",
                         "messages": []}).encode()),
                ctx)
        # Simulate a buffered response with usage.
        resp = {"usage": {"prompt_tokens": 3, "completion_tokens": 4,
                          "total_tokens": 7}}
        with patch.object(
                svc, "_transform_response_to_openai", return_value=resp):
            svc.on_response_body(
                service_pb2.HttpBody(
                    body=json.dumps(resp).encode(),
                    end_of_stream=True),
                ctx)
        spans = _spans(exporter)
        assert len(spans) == 1
        assert spans[0].attributes["litellm.usage.total_tokens"] == 7
        assert "litellm.request.original_model" not in spans[0].attributes
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()


def test_span_stamps_original_model_on_a_real_override(exporter):
    from extproc.example.litellm_gateway import gateway_config, routing
    with patch.dict(os.environ, {
            "GCP_PROJECT_ID": "p", "GCP_REGION": "us-central1"}):
        svc = LiteLLMGatewayCallout(
            disable_tls=True, plaintext_address=("0.0.0.0", 0))
    try:
        svc.telemetry = _telemetry(exporter)
        svc.router = routing.Router(gateway_config.RoutingSettings(
            model_group_alias={"fast": "vertex_ai/gemini-2.5-flash"},
            tag_rules={}, weighted_groups={}, shuffle_groups={}))
        ctx = _Ctx()
        # x-model-id names the served model; body names what the client
        # asked for. The header wins, so the original must be recorded.
        svc.on_request_headers(_hdrs({
            ":path": "/v1/chat/completions", ":method": "POST",
            "x-model-id": "anthropic/claude-haiku-4-5"}), ctx)
        pr = _ProviderRequest(
            api_base_url="https://api.anthropic.com/v1/messages",
            headers={"x-api-key": "k"}, body={"x": 1},
            provider="anthropic", model="claude-haiku-4-5")
        with patch.object(svc, "_build_provider_request", return_value=pr):
            svc.on_request_body(service_pb2.HttpBody(body=json.dumps(
                {"model": "vertex_ai/gemini-2.5-flash",
                 "messages": []}).encode()), ctx)
        resp = {"usage": {"prompt_tokens": 1, "completion_tokens": 1,
                          "total_tokens": 2}}
        with patch.object(
                svc, "_transform_response_to_openai", return_value=resp):
            svc.on_response_body(service_pb2.HttpBody(
                body=json.dumps(resp).encode(), end_of_stream=True), ctx)
        attrs = _spans(exporter)[0].attributes
        # The served model is what the header selected; the original is the
        # body model the client actually sent.
        assert attrs["gen_ai.request.model"] == "claude-haiku-4-5"
        assert attrs["litellm.request.original_model"] == (
            "vertex_ai/gemini-2.5-flash")
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()
