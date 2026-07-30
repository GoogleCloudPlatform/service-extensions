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

"""Unit tests for the LiteLLM Gateway Python callout.

Pure unit tests: no gRPC server started, no network calls. Phase methods are
called directly with synthetic proto objects. Provider transformations that
LiteLLM can do offline (Anthropic body transform, Vertex generateContent
response transform) are exercised against the real LiteLLM library; the parts
that need GCP credentials (Vertex ADC token minting) are patched out.
"""

import json
import os
from unittest.mock import patch

import fakeredis
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.litellm_gateway import gateway_config
from extproc.example.litellm_gateway import quota
from extproc.example.litellm_gateway import routing
from extproc.example.litellm_gateway import telemetry
from extproc.example.litellm_gateway.service_callout_example import (
    HEADER_LITELLM_MODEL,
    HEADER_LITELLM_PROVIDER,
    HEADER_LITELLM_ROUTED,
    HEADER_LITELLM_STREAMING,
    LiteLLMGatewayCallout,
    _ProviderRequest,
    _StreamState,
    _extract_sse_data,
    _state,
    _vertex_gemini_body,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _Ctx:
    """Minimal ServicerContext substitute that supports attribute assignment."""


def _http_headers(headers_dict: dict) -> service_pb2.HttpHeaders:
    hm = HeaderMap()
    for k, v in headers_dict.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.HttpHeaders(headers=hm)


def _body(body_bytes: bytes, end_of_stream: bool = False) -> service_pb2.HttpBody:
    return service_pb2.HttpBody(body=body_bytes, end_of_stream=end_of_stream)


def _set_headers(response) -> dict:
    """{key: decoded_value} from a BodyResponse / HeadersResponse mutation."""
    return {
        hvo.header.key: hvo.header.raw_value.decode()
        for hvo in response.response.header_mutation.set_headers
    }


@pytest.fixture(scope="module")
def svc():
    """Callout instance with no server started and no real GCP credentials."""
    with patch.dict(os.environ, {
        "GCP_PROJECT_ID": "test-project",
        "GCP_REGION": "us-central1",
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }):
        callout = LiteLLMGatewayCallout(
            disable_tls=True,
            plaintext_address=("0.0.0.0", 0),
        )
        try:
            yield callout
        finally:
            if callout._callout_server is not None:
                callout._callout_server.stop()


# A canned _ProviderRequest matching what `_build_provider_request` would
# return for a Vertex Gemini call. Used to patch out the GCP-credential
# dependent path (ADC token mint).
_VERTEX_PROVIDER_REQUEST = _ProviderRequest(
    api_base_url=(
        "https://us-central1-aiplatform.googleapis.com/v1/projects/test-project"
        "/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent"
    ),
    headers={"Authorization": "Bearer fake-adc-token", "content-type": "application/json"},
    body={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
    provider="vertex_ai",
    model="gemini-2.5-flash",
)


@pytest.fixture
def span_exporter():
    """An in-memory OTel span exporter installed as the active provider.

    Mirrors the `exporter` fixture in litellm_gateway_telemetry_test.py; kept
    local to this file so the request-header tests here don't need to import
    across test modules.
    """
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    telemetry._install_provider(provider)
    yield exp
    telemetry._reset()


# ---------------------------------------------------------------------------
# _extract_sse_data
# ---------------------------------------------------------------------------

class TestExtractSseData:
    def test_simple(self):
        assert _extract_sse_data('data: {"k":"v"}') == '{"k":"v"}'

    def test_strips_leading_space(self):
        assert _extract_sse_data("data:  hello") == "hello"

    def test_no_data_line_returns_none(self):
        assert _extract_sse_data("event: ping\nid: 1") is None

    def test_done_sentinel(self):
        assert _extract_sse_data("data: [DONE]") == "[DONE]"

    def test_multiple_data_lines_concatenated(self):
        assert _extract_sse_data("data: a\ndata: b") == "a\nb"

    def test_ignores_comment_and_event_lines(self):
        assert _extract_sse_data(": comment\nevent: x\ndata: payload") == "payload"


# ---------------------------------------------------------------------------
# _vertex_gemini_body  (OpenAI chat-completions → Vertex generateContent)
# ---------------------------------------------------------------------------

class TestVertexGeminiBody:
    def test_basic_user_message(self):
        out = _vertex_gemini_body({"messages": [{"role": "user", "content": "Hello"}]})
        assert out["contents"] == [{"role": "user", "parts": [{"text": "Hello"}]}]
        assert "systemInstruction" not in out

    def test_system_message_becomes_instruction(self):
        out = _vertex_gemini_body({"messages": [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "Hi"},
        ]})
        assert out["systemInstruction"] == {"parts": [{"text": "Be helpful."}]}
        assert len(out["contents"]) == 1

    def test_assistant_role_mapped_to_model(self):
        out = _vertex_gemini_body({"messages": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]})
        assert out["contents"][1]["role"] == "model"

    def test_generation_config_forwarded(self):
        out = _vertex_gemini_body({
            "messages": [{"role": "user", "content": "x"}],
            "temperature": 0.7,
            "max_tokens": 100,
            "top_p": 0.9,
        })
        cfg = out["generationConfig"]
        assert cfg["temperature"] == 0.7
        assert cfg["maxOutputTokens"] == 100
        assert cfg["topP"] == 0.9

    def test_no_gen_config_when_absent(self):
        out = _vertex_gemini_body({"messages": [{"role": "user", "content": "hi"}]})
        assert "generationConfig" not in out

    def test_non_string_content_serialized(self):
        out = _vertex_gemini_body({"messages": [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ]})
        # Falls back to json.dumps; the important thing is it doesn't crash.
        assert out["contents"][0]["parts"][0]["text"]

    def test_empty_messages(self):
        assert _vertex_gemini_body({"messages": []})["contents"] == []


# ---------------------------------------------------------------------------
# on_request_headers
# ---------------------------------------------------------------------------

class TestOnRequestHeaders:
    def test_non_llm_path_returns_none(self, svc):
        ctx = _Ctx()
        assert svc.on_request_headers(
            _http_headers({":path": "/healthz", ":method": "GET"}), ctx) is None

    def test_non_llm_path_does_not_mark_state(self, svc):
        ctx = _Ctx()
        svc.on_request_headers(_http_headers({":path": "/static/app.js", ":method": "GET"}), ctx)
        assert _state(ctx).is_llm is False

    def test_llm_path_returns_processing_response(self, svc):
        ctx = _Ctx()
        result = svc.on_request_headers(
            _http_headers({":path": "/v1/chat/completions", ":method": "POST"}), ctx)
        assert isinstance(result, service_pb2.ProcessingResponse)

    def test_llm_path_sets_routed_header(self, svc):
        ctx = _Ctx()
        result = svc.on_request_headers(
            _http_headers({":path": "/v1/chat/completions", ":method": "POST"}), ctx)
        hdrs = {
            hvo.header.key: hvo.header.raw_value.decode()
            for hvo in result.request_headers.response.header_mutation.set_headers
        }
        assert hdrs.get(HEADER_LITELLM_ROUTED) == "true"

    def test_llm_path_marks_state(self, svc):
        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({":path": "/v1/embeddings", ":method": "POST"}), ctx)
        assert _state(ctx).is_llm is True

    def test_disable_callbacks_header_skips_span(self, svc, span_exporter):
        # LiteLLM's x-litellm-disable-callbacks (a comma list); the span is
        # skipped only when the list contains "otel".
        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({
                ":path": "/v1/chat/completions",
                ":method": "POST",
                "x-litellm-disable-callbacks": "prometheus, otel",
            }), ctx)
        assert _state(ctx).span is None

        # Drive the request all the way through a response so an errant span
        # created elsewhere in the flow would still show up in the exporter.
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(
                svc, "_build_provider_request",
                return_value=_VERTEX_PROVIDER_REQUEST):
            svc.on_request_body(_body(body), ctx)
        resp = {"usage": {
            "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        with patch.object(
                svc, "_transform_response_to_openai", return_value=resp):
            svc.on_response_body(
                _body(json.dumps(resp).encode(), end_of_stream=True), ctx)

        assert not span_exporter.get_finished_spans()

    def test_disable_callbacks_without_otel_still_spans(
            self, svc, span_exporter):
        # Sanity check for the comma-list parsing: a disable list that does
        # not name "otel" must not suppress the span.
        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({
                ":path": "/v1/chat/completions",
                ":method": "POST",
                "x-litellm-disable-callbacks": "prometheus",
            }), ctx)
        assert _state(ctx).span is not None


# ---------------------------------------------------------------------------
# on_request_body
# ---------------------------------------------------------------------------

class TestOnRequestBody:
    def test_not_llm_returns_none(self, svc):
        ctx = _Ctx()
        assert svc.on_request_body(_body(b'{"model":"x"}'), ctx) is None

    def test_empty_body_returns_body_response(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        assert isinstance(svc.on_request_body(_body(b""), ctx), service_pb2.BodyResponse)

    def test_invalid_json_returns_400(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        result = svc.on_request_body(_body(b"not-json"), ctx)
        assert isinstance(result, service_pb2.ImmediateResponse)
        assert result.status.code == 400

    def test_missing_model_returns_400(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        result = svc.on_request_body(_body(b'{"messages":[]}'), ctx)
        assert isinstance(result, service_pb2.ImmediateResponse)
        assert result.status.code == 400

    def test_litellm_transform_failure_returns_500(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        body = json.dumps({"model": "vertex_ai/gemini-2.5-flash", "messages": []}).encode()
        with patch.object(svc, "_build_provider_request", side_effect=RuntimeError("boom")):
            result = svc.on_request_body(_body(body), ctx)
        assert isinstance(result, service_pb2.ImmediateResponse)
        assert result.status.code == 500

    def test_vertex_request_rewrites_path_authority_auth(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(svc, "_build_provider_request", return_value=_VERTEX_PROVIDER_REQUEST):
            result = svc.on_request_body(_body(body), ctx)
        assert isinstance(result, service_pb2.BodyResponse)
        hdrs = _set_headers(result)
        assert hdrs[":path"].startswith("/v1/projects/test-project")
        assert hdrs[":path"].endswith(":generateContent")
        assert hdrs[":authority"] == "us-central1-aiplatform.googleapis.com"
        assert hdrs["host"] == "us-central1-aiplatform.googleapis.com"
        assert hdrs["authorization"] == "Bearer fake-adc-token"

    def test_provenance_headers_set(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(svc, "_build_provider_request", return_value=_VERTEX_PROVIDER_REQUEST):
            result = svc.on_request_body(_body(body), ctx)
        hdrs = _set_headers(result)
        assert hdrs[HEADER_LITELLM_PROVIDER] == "vertex_ai"
        assert hdrs[HEADER_LITELLM_MODEL] == "gemini-2.5-flash"
        assert hdrs[HEADER_LITELLM_STREAMING] == "false"

    def test_content_length_matches_new_body(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(svc, "_build_provider_request", return_value=_VERTEX_PROVIDER_REQUEST):
            result = svc.on_request_body(_body(body), ctx)
        hdrs = _set_headers(result)
        assert hdrs["content-length"] == str(len(result.response.body_mutation.body))

    def test_no_clear_route_cache(self, svc):
        # Traffic extensions can't switch backends; we must not set this.
        ctx = _Ctx()
        _state(ctx).is_llm = True
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(svc, "_build_provider_request", return_value=_VERTEX_PROVIDER_REQUEST):
            result = svc.on_request_body(_body(body), ctx)
        assert result.response.clear_route_cache is False

    def test_streaming_flag_recorded(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(svc, "_build_provider_request", return_value=_VERTEX_PROVIDER_REQUEST):
            result = svc.on_request_body(_body(body), ctx)
        assert _state(ctx).is_streaming is True
        assert _set_headers(result)[HEADER_LITELLM_STREAMING] == "true"

    def test_anthropic_request_end_to_end(self, svc):
        # Exercises the real LiteLLM AnthropicConfig path; no network needed.
        ctx = _Ctx()
        _state(ctx).is_llm = True
        body = json.dumps({
            "model": "anthropic/claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
        }).encode()
        result = svc.on_request_body(_body(body), ctx)
        assert isinstance(result, service_pb2.BodyResponse)
        hdrs = _set_headers(result)
        assert hdrs[":authority"] == "api.anthropic.com"
        assert hdrs[":path"] == "/v1/messages"
        assert hdrs["x-api-key"] == "sk-ant-test"
        assert "anthropic-version" in hdrs
        assert hdrs["anthropic-dangerous-direct-browser-access"] == "true"
        assert hdrs[HEADER_LITELLM_PROVIDER] == "anthropic"
        # Body should be Anthropic Messages format. LiteLLM normalizes string
        # content to the structured [{"type":"text","text":...}] form.
        new_body = json.loads(result.response.body_mutation.body)
        assert new_body["max_tokens"] == 64
        msg = new_body["messages"][0]
        assert msg["role"] == "user"
        text = msg["content"] if isinstance(msg["content"], str) else msg["content"][0]["text"]
        assert text == "hi"

    @staticmethod
    def _enable_routing():
        """Turn the routing feature flag on (any non-empty table)."""
        routing.configure(gateway_config.RoutingSettings(
            model_group_alias={"fast": "vertex_ai/gemini-2.5-flash"},
            tag_rules={}, weighted_groups={}, shuffle_groups={}))

    def test_header_model_overrides_body_model(self, svc):
        # With routing enabled, the LB already routed on an x-model-id the
        # route extension may have rewritten, so when it disagrees with the
        # body's model the header wins: it names the model the backend was
        # actually chosen for.
        self._enable_routing()
        try:
            ctx = _Ctx()
            svc.on_request_headers(
                _http_headers({
                    ":path": "/v1/chat/completions",
                    ":method": "POST",
                    "x-model-id": "anthropic/claude-haiku-4-5",
                }), ctx)
            body = json.dumps({
                "model": "vertex_ai/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}],
            }).encode()
            result = svc.on_request_body(_body(body), ctx)
            assert isinstance(result, service_pb2.BodyResponse)
            hdrs = _set_headers(result)
            assert hdrs[":authority"] == "api.anthropic.com"
            assert hdrs[HEADER_LITELLM_MODEL] == "claude-haiku-4-5"
        finally:
            routing._reset()

    def test_flag_off_keeps_body_model(self, svc):
        # Routing disabled (the default): the header never overrides the
        # body model, preserving the original gateway behavior exactly.
        assert routing.enabled() is False
        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({
                ":path": "/v1/chat/completions",
                ":method": "POST",
                "x-model-id": "anthropic/claude-haiku-4-5",
            }), ctx)
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(
                svc, "_build_provider_request",
                return_value=_VERTEX_PROVIDER_REQUEST) as mock_build:
            svc.on_request_body(_body(body), ctx)
        args, _ = mock_build.call_args
        assert args[0] == "vertex_ai/gemini-2.5-flash"
        assert args[1]["model"] == "vertex_ai/gemini-2.5-flash"

    def test_alias_header_does_not_override(self, svc):
        # Even with routing enabled, "cheap" is a routing alias (resolved by
        # the route extension before this callout runs), not a LiteLLM model
        # id: it has no known provider prefix, so it must not override the
        # body model.
        self._enable_routing()
        try:
            ctx = _Ctx()
            svc.on_request_headers(
                _http_headers({
                    ":path": "/v1/chat/completions",
                    ":method": "POST",
                    "x-model-id": "cheap",
                }), ctx)
            body = json.dumps({
                "model": "vertex_ai/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}],
            }).encode()
            with patch.object(
                    svc, "_build_provider_request",
                    return_value=_VERTEX_PROVIDER_REQUEST) as mock_build:
                result = svc.on_request_body(_body(body), ctx)
            hdrs = _set_headers(result)
            assert hdrs[HEADER_LITELLM_PROVIDER] == "vertex_ai"
            assert hdrs[HEADER_LITELLM_MODEL] == "gemini-2.5-flash"

            # The alias "cheap" must never reach the transform: the guard
            # has to leave the body model in place both as the positional
            # arg and inside req_map, or this assertion catches the
            # regression.
            args, _ = mock_build.call_args
            assert args[0] == "vertex_ai/gemini-2.5-flash"
            assert args[1]["model"] == "vertex_ai/gemini-2.5-flash"
        finally:
            routing._reset()


# ---------------------------------------------------------------------------
# on_response_headers
# ---------------------------------------------------------------------------

class TestOnResponseHeaders:
    def test_not_llm_returns_empty_headers_response(self, svc):
        ctx = _Ctx()
        result = svc.on_response_headers(_http_headers({"content-type": "text/plain"}), ctx)
        assert isinstance(result, service_pb2.HeadersResponse)
        assert not result.response.header_mutation.remove_headers

    def test_llm_removes_content_length(self, svc):
        ctx = _Ctx()
        _state(ctx).is_llm = True
        result = svc.on_response_headers(
            _http_headers({"content-length": "1234"}), ctx)
        removed = result.response.header_mutation.remove_headers
        assert "content-length" in removed

    def test_response_headers_include_call_id_and_usage(self, svc):
        # Seed a fakeredis-backed quota key (as the quota wiring tests do),
        # run the request-headers and request-body legs to populate state
        # (call_id, api_key) and record some spend, then check the
        # response-headers leg surfaces both the call id and the quota
        # usage headers while still removing content-length.
        client = fakeredis.FakeRedis(decode_responses=True)
        quota._set_client(client)
        try:
            client.hset("key:vk1", mapping={
                "token_budget": "1000", "budget_duration": "30d"})
            ctx = _Ctx()
            svc.on_request_headers(
                _http_headers({
                    ":path": "/v1/chat/completions",
                    ":method": "POST",
                    "authorization": "Bearer vk1",
                }), ctx)
            body = json.dumps({
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 16,
            }).encode()
            svc.on_request_body(_body(body), ctx)
            quota.record("vk1", "anthropic/claude-haiku-4-5", 50)

            result = svc.on_response_headers(
                _http_headers({"content-length": "1234"}), ctx)

            removed = result.response.header_mutation.remove_headers
            assert "content-length" in removed
            hdrs = _set_headers(result)
            assert hdrs["x-litellm-call-id"] == _state(ctx).call_id
            assert hdrs["x-litellm-key-spend"] == "50"
        finally:
            quota._reset()


# ---------------------------------------------------------------------------
# Upstream status propagation: the telemetry span must reflect the real
# provider response status, not a hardcoded 200.
# ---------------------------------------------------------------------------

class TestUpstreamStatusInSpan:
    def test_error_status_propagates_to_span(self, svc, span_exporter):
        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({
                ":path": "/v1/chat/completions",
                ":method": "POST",
            }), ctx)
        body = json.dumps({
            "model": "vertex_ai/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        with patch.object(
                svc, "_build_provider_request",
                return_value=_VERTEX_PROVIDER_REQUEST):
            svc.on_request_body(_body(body), ctx)
        svc.on_response_headers(_http_headers({":status": "429"}), ctx)
        resp = {"usage": {
            "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        with patch.object(
                svc, "_transform_response_to_openai", return_value=resp):
            svc.on_response_body(
                _body(json.dumps(resp).encode(), end_of_stream=True), ctx)
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["http.response.status_code"] == 429


# ---------------------------------------------------------------------------
# Quota model-id wiring: check() metering must match record() bookkeeping.
# ---------------------------------------------------------------------------

class TestQuotaModelIdWiring:
    def test_check_and_record_share_full_model_id(self, svc):
        # Regression test: quota.check() on the request leg metered
        # model_max_budget against the full LiteLLM model id (post
        # header-override), while quota.record() on the response leg used
        # to write the provider-stripped id (state.model). That meant
        # record() never wrote the counter check() read, so per-model
        # budgets were silently never enforced. state.quota_model fixes
        # this by carrying the same full id through both legs.
        client = fakeredis.FakeRedis(decode_responses=True)
        quota._set_client(client)
        try:
            full_model = "anthropic/claude-haiku-4-5"
            client.hset("key:vk1", mapping={
                "model_max_budget": json.dumps({
                    full_model: {"budget_limit": 20, "time_period": "1d"},
                }),
            })

            def _drive():
                ctx = _Ctx()
                svc.on_request_headers(_http_headers({
                    ":path": "/v1/chat/completions",
                    ":method": "POST",
                    "authorization": "Bearer vk1",
                }), ctx)
                body = json.dumps({
                    "model": full_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 16,
                }).encode()
                return ctx, svc.on_request_body(_body(body), ctx)

            ctx, result = _drive()
            assert isinstance(result, service_pb2.BodyResponse)

            resp = {"usage": {
                "prompt_tokens": 10, "completion_tokens": 15,
                "total_tokens": 25}}
            with patch.object(
                    svc, "_transform_response_to_openai", return_value=resp):
                svc.on_response_body(
                    _body(json.dumps(resp).encode(), end_of_stream=True),
                    ctx)

            window = quota._window_id("1d")
            per_model_key = f"spend:vk1:{full_model}:{window}"
            assert int(client.get(per_model_key) or 0) == 25

            # Spend (25) now exceeds budget_limit (20); the next request for
            # the same model is rejected with 402 before it reaches LiteLLM.
            ctx2, result2 = _drive()
            assert isinstance(result2, service_pb2.ImmediateResponse)
            assert result2.status.code == 402
        finally:
            quota._reset()


# ---------------------------------------------------------------------------
# Streaming usage capture: token totals surfaced on a streamed chunk.
# ---------------------------------------------------------------------------

class TestStreamingUsageCapture:
    def test_message_delta_usage_merged_and_recorded(self, svc):
        # Anthropic surfaces usage on the final `message_delta` SSE event.
        # _handle_streaming_chunk must merge it into state.usage so the
        # end_of_stream leg in on_response_body can meter it via
        # quota.record(), same as a buffered response.
        client = fakeredis.FakeRedis(decode_responses=True)
        quota._set_client(client)
        try:
            client.hset("key:vk1", mapping={
                "token_budget": 1000, "budget_duration": "30d"})
            ctx = _Ctx()
            state = _state(ctx)
            state.is_llm = True
            state.is_streaming = True
            state.provider = "anthropic"
            state.model = "claude-haiku-4-5"
            state.quota_model = "anthropic/claude-haiku-4-5"
            state.api_key = "vk1"
            state.request_body = {
                "messages": [{"role": "user", "content": "hi"}]}

            event = json.dumps({
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }).encode()
            svc.on_response_body(
                _body(b"data: " + event + b"\n\n", end_of_stream=False), ctx)
            assert state.usage.get("total_tokens") == 15

            svc.on_response_body(_body(b"", end_of_stream=True), ctx)

            window = quota._window_id("30d")
            spend = int(client.get(f"spend:vk1:{window}") or 0)
            assert spend == 15
        finally:
            quota._reset()

    def test_split_usage_across_events_not_clobbered(self, svc):
        # Real Anthropic streams split usage across two events: an early
        # `message_start` carries the real prompt_tokens count, and the
        # closing `message_delta` carries only output_tokens, so LiteLLM
        # fills prompt_tokens with a 0 placeholder on that later event. A
        # naive overwrite-merge would let that placeholder replace the real
        # prompt count (10 -> 0), undercounting spend as 5 instead of 15.
        client = fakeredis.FakeRedis(decode_responses=True)
        quota._set_client(client)
        try:
            client.hset("key:vk1", mapping={
                "token_budget": 1000, "budget_duration": "30d"})
            ctx = _Ctx()
            state = _state(ctx)
            state.is_llm = True
            state.is_streaming = True
            state.provider = "anthropic"
            state.model = "claude-haiku-4-5"
            state.quota_model = "anthropic/claude-haiku-4-5"
            state.api_key = "vk1"
            state.request_body = {
                "messages": [{"role": "user", "content": "hi"}]}

            # message_start: prompt_tokens=10, completion_tokens=1,
            # total_tokens=11.
            message_start = json.dumps({
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-haiku-4-5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            }).encode()
            svc.on_response_body(
                _body(b"data: " + message_start + b"\n\n",
                      end_of_stream=False),
                ctx)
            assert state.usage.get("prompt_tokens") == 10
            assert state.usage.get("total_tokens") == 11

            # message_delta: no input_tokens key, so LiteLLM defaults
            # prompt_tokens to 0; completion_tokens=5, total_tokens=5.
            message_delta = json.dumps({
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 5},
            }).encode()
            svc.on_response_body(
                _body(b"data: " + message_delta + b"\n\n",
                      end_of_stream=False),
                ctx)
            # The real prompt_tokens count must survive the zero placeholder.
            assert state.usage.get("prompt_tokens") == 10
            assert state.usage.get("completion_tokens") == 5
            assert state.usage.get("total_tokens") == 15

            svc.on_response_body(_body(b"", end_of_stream=True), ctx)

            window = quota._window_id("30d")
            spend = int(client.get(f"spend:vk1:{window}") or 0)
            assert spend == 15
        finally:
            quota._reset()


# ---------------------------------------------------------------------------
# on_response_body  (dispatch)
# ---------------------------------------------------------------------------

class TestOnResponseBody:
    def test_not_llm_returns_none(self, svc):
        ctx = _Ctx()
        assert svc.on_response_body(_body(b"whatever"), ctx) is None

    def test_buffered_path_dispatched(self, svc):
        ctx = _Ctx()
        st = _state(ctx)
        st.is_llm = True
        st.is_streaming = False
        st.model = "gemini-2.5-flash"
        st.provider = "vertex_ai"
        result = svc.on_response_body(_body(b"partial", end_of_stream=False), ctx)
        # Intermediate chunk in buffered mode → body suppressed.
        assert result.response.body_mutation.body == b""

    def test_streaming_path_dispatched(self, svc):
        ctx = _Ctx()
        st = _state(ctx)
        st.is_llm = True
        st.is_streaming = True
        st.provider = "openai"  # pass-through
        result = svc.on_response_body(_body(b"data: x\n\n", end_of_stream=False), ctx)
        assert isinstance(result, service_pb2.BodyResponse)


# ---------------------------------------------------------------------------
# _handle_buffered_chunk
# ---------------------------------------------------------------------------

class TestHandleBufferedChunk:
    def test_intermediate_chunk_suppressed(self, svc):
        state = _StreamState(model="m", provider="vertex_ai")
        result = svc._handle_buffered_chunk(state, b"partial", end_of_stream=False)
        assert result.response.body_mutation.body == b""

    def test_accumulates_across_chunks(self, svc):
        state = _StreamState(model="m", provider="vertex_ai")
        svc._handle_buffered_chunk(state, b"abc", end_of_stream=False)
        svc._handle_buffered_chunk(state, b"def", end_of_stream=False)
        assert bytes(state.body_buffer) == b"abcdef"

    def test_vertex_response_transformed_to_openai_on_eos(self, svc):
        state = _StreamState(
            model="gemini-2.5-flash", provider="vertex_ai",
            request_body={"messages": [{"role": "user", "content": "hi"}]},
        )
        vertex_resp = {
            "candidates": [{
                "content": {"role": "model", "parts": [{"text": "Hello!"}]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {
                "promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8,
            },
            "modelVersion": "gemini-2.5-flash",
        }
        result = svc._handle_buffered_chunk(
            state, json.dumps(vertex_resp).encode(), end_of_stream=True)
        out = json.loads(result.response.body_mutation.body)
        assert out["object"] == "chat.completion"
        assert out["choices"][0]["message"]["content"] == "Hello!"
        assert out["choices"][0]["message"]["role"] == "assistant"

    def test_invalid_json_passes_raw_body_on_eos(self, svc):
        state = _StreamState(model="m", provider="vertex_ai")
        raw = b"not-valid-json"
        result = svc._handle_buffered_chunk(state, raw, end_of_stream=True)
        assert result.response.body_mutation.body == raw

    def test_unknown_provider_passes_through_on_eos(self, svc):
        state = _StreamState(model="m", provider="not-a-real-provider")
        raw = json.dumps({"choices": [{"message": {"content": "x"}}]}).encode()
        result = svc._handle_buffered_chunk(state, raw, end_of_stream=True)
        # Falls back to returning the parsed JSON unchanged.
        assert json.loads(result.response.body_mutation.body) == json.loads(raw)


# ---------------------------------------------------------------------------
# _handle_streaming_chunk
# ---------------------------------------------------------------------------

class TestHandleStreamingChunk:
    def test_openai_compat_provider_passes_through(self, svc):
        state = _StreamState(model="m", provider="openai")
        raw = b"data: {\"choices\":[]}\n\n"
        result = svc._handle_streaming_chunk(state, raw, end_of_stream=False)
        assert result.response.body_mutation.body == raw

    def test_done_appended_on_eos_for_transforming_provider(self, svc):
        state = _StreamState(model="gemini-2.5-flash", provider="vertex_ai")
        result = svc._handle_streaming_chunk(state, b"", end_of_stream=True)
        assert b"data: [DONE]\n\n" in result.response.body_mutation.body

    def test_partial_event_held_in_buffer(self, svc):
        state = _StreamState(model="gemini-2.5-flash", provider="vertex_ai")
        result = svc._handle_streaming_chunk(state, b"data: {", end_of_stream=False)
        assert result.response.body_mutation.body == b""
        assert "data: {" in state.sse_buffer

    def test_done_sentinel_in_stream_skipped(self, svc):
        state = _StreamState(model="gemini-2.5-flash", provider="vertex_ai")
        result = svc._handle_streaming_chunk(state, b"data: [DONE]\n\n", end_of_stream=False)
        assert result.response.body_mutation.body == b""

    def test_non_json_sse_data_skipped(self, svc):
        state = _StreamState(model="gemini-2.5-flash", provider="vertex_ai")
        result = svc._handle_streaming_chunk(state, b"data: not-json\n\n", end_of_stream=False)
        assert result.response.body_mutation.body == b""

    def test_crlf_normalized(self, svc):
        # Vertex emits CRLF-delimited SSE; ensure we still split events.
        state = _StreamState(model="gemini-2.5-flash", provider="vertex_ai")
        # An empty/comment event with CRLF; should consume cleanly, no crash.
        svc._handle_streaming_chunk(state, b": ping\r\n\r\n", end_of_stream=False)
        assert state.sse_buffer == ""
