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

Pure unit tests — no gRPC server started, no network calls. Phase methods are
called directly with synthetic proto objects. Provider transformations that
LiteLLM can do offline (Anthropic body transform, Vertex generateContent
response transform) are exercised against the real LiteLLM library; the parts
that need GCP credentials (Vertex ADC token minting) are patched out.
"""

import json
import os
from unittest.mock import patch

import pytest

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2

from extproc.example.litellm_gateway.service_callout_example import (
    HEADER_LITELLM_MODEL,
    HEADER_LITELLM_PROVIDER,
    HEADER_LITELLM_ROUTED,
    HEADER_LITELLM_STREAMING,
    LiteLLMGatewayCallout,
    _StreamState,
    _extract_sse_data,
    _state,
    _vertex_gemini_body,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _Ctx:
    """Minimal ServicerContext substitute — supports attribute assignment."""


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
    """Callout instance — no server started, no real GCP credentials."""
    with patch.dict(os.environ, {
        "GCP_PROJECT_ID": "test-project",
        "GCP_REGION": "us-central1",
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }):
        yield LiteLLMGatewayCallout(disable_tls=True)


# A canned (URL, headers, body, provider, model) tuple matching what
# _build_provider_request would return for a Vertex Gemini request — used to
# patch out the GCP-credential-dependent path.
_VERTEX_PROVIDER_REQUEST = (
    "https://us-central1-aiplatform.googleapis.com/v1/projects/test-project"
    "/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent",
    {"Authorization": "Bearer fake-adc-token", "content-type": "application/json"},
    {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
    "vertex_ai",
    "gemini-2.5-flash",
)


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
        # Falls back to json.dumps — the important thing is it doesn't crash.
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
        # Exercises the real LiteLLM AnthropicConfig path — no network needed.
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
        result = svc.on_response_headers(_http_headers({"content-length": "1234"}), ctx)
        assert "content-length" in result.response.header_mutation.remove_headers


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
        # An empty/comment event with CRLF — should consume cleanly, no crash.
        svc._handle_streaming_chunk(state, b": ping\r\n\r\n", end_of_stream=False)
        assert state.sse_buffer == ""
