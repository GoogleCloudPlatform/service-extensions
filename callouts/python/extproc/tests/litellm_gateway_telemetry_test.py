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
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.litellm_gateway import gateway_config, telemetry
from extproc.example.litellm_gateway.service_callout_example import (
    LiteLLMGatewayCallout, _ProviderRequest, _state,
)


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    telemetry._install_provider(provider)
    yield exp
    telemetry._reset()


@pytest.fixture(autouse=True)
def reset_gateway_config():
    gateway_config._reset()
    yield
    gateway_config._reset()


class _Ctx:
    pass


def _hdrs(d):
    hm = HeaderMap()
    for k, v in d.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.HttpHeaders(headers=hm)


def test_span_carries_genai_attributes(exporter):
    span = telemetry.start_request_span({})
    telemetry.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=10, completion_tokens=5, total_tokens=15,
        status=200, streaming=False)
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.request.model"] == "claude-haiku-4-5"
    assert attrs["gen_ai.usage.total_tokens"] == 15
    assert attrs["http.response.status_code"] == 200


def test_new_span_attributes(exporter):
    span = telemetry.start_request_span({})
    telemetry.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=9, completion_tokens=16, total_tokens=25,
        status=200, streaming=True, operation="chat",
        api_key="vk-secret", call_id="call-123")
    exported = exporter.get_finished_spans()[0]
    attrs = exported.attributes
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["litellm.call_id"] == "call-123"
    assert attrs["llm.is_streaming"] is True
    assert "llm.streaming" not in attrs
    key_hash = attrs["user_api_key_hash"]
    assert len(key_hash) == 16 and "vk-secret" not in key_hash
    # Known Anthropic model: cost should resolve to a positive float.
    assert attrs["gen_ai.cost.total_cost"] > 0


def test_redact_key_info(exporter):
    gateway_config._load_dict(
        {"litellm_settings": {"redact_user_api_key_info": True}})
    span = telemetry.start_request_span({})
    telemetry.end_request_span(
        span, provider="anthropic", model="claude-haiku-4-5",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        status=200, streaming=False, api_key="vk-secret")
    attrs = exporter.get_finished_spans()[0].attributes
    assert "user_api_key_hash" not in attrs


def test_unknown_model_omits_cost(exporter):
    span = telemetry.start_request_span({})
    telemetry.end_request_span(
        span, provider="nope", model="not-a-real-model",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        status=200, streaming=False)
    attrs = exporter.get_finished_spans()[0].attributes
    assert "gen_ai.cost.total_cost" not in attrs


def test_inert_when_disabled():
    telemetry._reset()
    assert telemetry.enabled() is False
    assert telemetry.start_request_span({}) is None
    # Must not raise on a None span.
    telemetry.end_request_span(
        None, provider="x", model="y", prompt_tokens=None,
        completion_tokens=None, total_tokens=None, status=200, streaming=False)


def test_span_emitted_for_full_request(exporter):
    with patch.dict(
            os.environ,
            {"GCP_PROJECT_ID": "p", "GCP_REGION": "us-central1"}):
        svc = LiteLLMGatewayCallout(
            disable_tls=True, plaintext_address=("0.0.0.0", 0))
    try:
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
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["gen_ai.usage.total_tokens"] == 7
    finally:
        if svc._callout_server is not None:
            svc._callout_server.stop()
