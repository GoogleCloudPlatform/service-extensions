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

"""LiteLLM Gateway callout — pure ext_proc adapter.

The callout is intentionally thin: it inspects the path, hands the OpenAI body
to LiteLLM for translation (auth, body transform, target URL), and applies the
result as ext_proc header + body mutations. The Cloud Load Balancer then
forwards the rewritten request to the provider via an Internet NEG backend.

Routing model: the LB's URL map picks the provider backend from the client's
`x-v2-target-provider` header — *before* this callout fires. GCP Service
Extensions don't allow body-based routing on a single LB (route extensions
can't read the body, traffic extensions can't change the backend), so the
header is the routing signal. Once the LB has picked the right backend, this
traffic-extension callout transforms the body and headers in flight.

LiteLLM owns:
  * provider detection (`litellm.get_llm_provider`)
  * OpenAI -> provider request body transform
  * auth (ADC for Vertex AI via Cloud Run service identity, env-var API keys
    for Anthropic / Groq / OpenRouter / etc.)
  * provider response -> OpenAI ModelResponse transform
  * SSE chunk parsing for streaming responses

The callout owns:
  * Envoy ext_proc protobuf adapter
  * :path / :authority / Authorization header rewriting on the upstream call
  * Stamping `x-litellm-*` provenance headers for observability
"""

import datetime
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx
from grpc import ServicerContext

import litellm
from litellm import ModelResponse
from litellm.litellm_core_utils.litellm_logging import Logging as LiteLLMLogging
from litellm.types.utils import LlmProviders
from litellm.utils import ProviderConfigManager

from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import ProcessingMode
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.service import callout_server
from extproc.service import callout_tools


# Provenance headers stamped on the forwarded request. Observability only —
# they don't affect routing (the LB already routed on the client's
# x-v2-target-provider header before this callout ran).
HEADER_LITELLM_ROUTED = "x-litellm-routed"
HEADER_LITELLM_PROVIDER = "x-litellm-provider"
HEADER_LITELLM_MODEL = "x-litellm-model"
HEADER_LITELLM_STREAMING = "x-litellm-streaming"

# OpenAI-compatible paths the callout intercepts. Anything else is a no-op.
LLM_ENDPOINTS = frozenset({
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/embeddings",
    "/v1/models",
    "/chat/completions",
    "/completions",
    "/embeddings",
})

# Headers the callout manages itself — never copy these from LiteLLM's output.
_MANAGED_HEADERS = frozenset({
    "host", ":authority", ":path", "content-length", "content-type",
})

# Default API bases by provider. LiteLLM's BaseConfig.get_complete_url() raises
# "api_base is required" when no base is supplied; the SDK normally resolves
# this inside `litellm.completion()`. We do it ourselves since we drive the
# config classes directly.
#
# Anthropic uses /v1/messages directly (not /v1/chat/completions like the
# OpenAI-compatible providers), so we include the path in the base.
_PROVIDER_API_BASE = {
    "anthropic":  "https://api.anthropic.com/v1/messages",
    "groq":       "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral":    "https://api.mistral.ai/v1",
    "deepseek":   "https://api.deepseek.com",
    "openai":     "https://api.openai.com/v1",
}

@dataclass
class _StreamState:
    is_llm: bool = False
    is_streaming: bool = False
    model: str = ""
    provider: str = ""
    request_body: dict = field(default_factory=dict)
    body_buffer: bytearray = field(default_factory=bytearray)
    sse_buffer: str = ""
    stream_iterator: Any = None
    stream_iterator_resolved: bool = False


def _state(context: ServicerContext) -> _StreamState:
    state = getattr(context, "_litellm_state", None)
    if state is None:
        state = _StreamState()
        context._litellm_state = state
    return state


class LiteLLMGatewayCallout(callout_server.CalloutServer):
    """Ext_proc callout that delegates all LLM work to LiteLLM."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.gcp_project = os.getenv("GCP_PROJECT_ID", "")
        self.gcp_region = os.getenv("GCP_REGION", "us-central1")
        if not self.gcp_project:
            logging.warning(
                "GCP_PROJECT_ID is unset; Vertex AI requests will fail.")

    def process(self, callout, context):
        """Set response_body_mode on the response_headers reply.

        On the response_headers event we tell the LB how to deliver the
        response body to us: STREAMED for SSE (so we can transform chunks
        on the fly), BUFFERED for everything else (so the response body
        arrives whole and we can run LiteLLM's transform_response over it).
        """
        resp = super().process(callout, context)
        if resp.HasField("immediate_response"):
            return resp
        if callout.HasField("response_headers"):
            state = _state(context)
            mode = ProcessingMode()
            mode.response_body_mode = (
                ProcessingMode.STREAMED if state.is_streaming else ProcessingMode.BUFFERED
            )
            resp.mode_override.CopyFrom(mode)
        return resp

    # ------------------------------------------------------------------ phases

    def on_request_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.ProcessingResponse | None:
        path, method = "", ""
        for h in headers.headers.headers:
            if h.key == ":path":
                path = h.raw_value.decode("utf-8")
            elif h.key == ":method":
                method = h.raw_value.decode("utf-8")
        logging.info("Request %s %s", method, path)

        if path not in LLM_ENDPOINTS:
            return None

        state = _state(context)
        state.is_llm = True

        resp = service_pb2.ProcessingResponse()
        resp.request_headers.response.header_mutation.set_headers.append(
            HeaderValueOption(
                header=HeaderValue(key=HEADER_LITELLM_ROUTED, raw_value=b"true")))

        return resp

    def on_request_body(
        self,
        body: service_pb2.HttpBody,
        context: ServicerContext,
    ) -> service_pb2.BodyResponse | service_pb2.ImmediateResponse | None:
        state = _state(context)
        if not state.is_llm:
            return None

        raw = body.body
        if not raw:
            return service_pb2.BodyResponse()

        try:
            req_map = json.loads(raw)
        except json.JSONDecodeError as e:
            logging.warning("Invalid JSON body: %s", e)
            return callout_tools.header_immediate_response(StatusCode.BadRequest)

        model = req_map.get("model")
        if not isinstance(model, str) or not model:
            logging.warning("Request missing 'model' field")
            return callout_tools.header_immediate_response(StatusCode.BadRequest)

        try:
            api_base, headers_dict, body_dict, provider, model_name = (
                self._build_provider_request(model, req_map)
            )
        except Exception:
            logging.exception("LiteLLM request transformation failed")
            return callout_tools.header_immediate_response(
                StatusCode.InternalServerError)

        state.model = model_name
        state.provider = provider
        state.is_streaming = bool(req_map.get("stream"))
        state.request_body = req_map

        new_body = json.dumps(body_dict).encode("utf-8")

        parsed = urlsplit(api_base)
        target_authority = parsed.netloc
        target_path = parsed.path or "/"
        if parsed.query:
            target_path = f"{target_path}?{parsed.query}"

        logging.info(
            "Routing :authority=%s :path=%s (provider=%s, streaming=%s)",
            target_authority, target_path, provider, state.is_streaming,
        )

        body_resp = service_pb2.BodyResponse()
        body_resp.response.body_mutation.body = new_body

        rewrites: list[tuple[str, str]] = [
            (":path", target_path),
            (":authority", target_authority),
            ("host", target_authority),
            ("content-type", "application/json"),
            ("content-length", str(len(new_body))),
            # Prevent gzip — the response transformation needs raw JSON bytes.
            ("accept-encoding", "identity"),
            # Some upstreams (Groq via Cloudflare) reject requests with no
            # User-Agent (or a generic "Google-LB" UA) as bot traffic.
            ("user-agent", "litellm-gateway/1.0"),
            # Provenance markers — observability only, not routing.
            (HEADER_LITELLM_PROVIDER, provider),
            (HEADER_LITELLM_MODEL, model_name),
            (HEADER_LITELLM_STREAMING, "true" if state.is_streaming else "false"),
        ]
        # Apply the auth + provider-specific headers LiteLLM computed
        # (Authorization: Bearer <ADC token>, x-api-key, anthropic-version, …).
        for k, v in headers_dict.items():
            if k.lower() in _MANAGED_HEADERS:
                continue
            rewrites.append((k.lower(), str(v)))

        for k, v in rewrites:
            body_resp.response.header_mutation.set_headers.append(
                HeaderValueOption(
                    header=HeaderValue(key=k, raw_value=v.encode("utf-8")),
                    append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
                ))

        # We don't set clear_route_cache here. GCP traffic extensions can't
        # switch backends after URL map evaluation — routing was already
        # decided by the URL map's header_matches on x-v2-target-provider.
        return body_resp

    def on_response_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.HeadersResponse | None:
        state = _state(context)
        if not state.is_llm:
            return service_pb2.HeadersResponse()
        resp = service_pb2.HeadersResponse()
        # Provider's Content-Length will be wrong after our body transform —
        # drop it so Envoy switches to chunked transfer encoding.
        resp.response.header_mutation.remove_headers.append("content-length")
        return resp

    def on_response_body(
        self,
        body: service_pb2.HttpBody,
        context: ServicerContext,
    ) -> service_pb2.BodyResponse | None:
        state = _state(context)
        if not state.is_llm:
            return None
        if state.is_streaming:
            return self._handle_streaming_chunk(
                state, body.body or b"", bool(body.end_of_stream))
        return self._handle_buffered_chunk(
            state, body.body or b"", bool(body.end_of_stream))

    # ------------------------------------------------------------- LiteLLM

    def _build_provider_request(
        self,
        model: str,
        req_map: dict,
    ) -> tuple[str, dict, dict, str, str]:
        """Drive LiteLLM provider config to produce (URL, headers, body)."""
        model_name, provider, _, _ = litellm.get_llm_provider(model=model)

        try:
            provider_enum = LlmProviders(provider)
        except ValueError as e:
            raise RuntimeError(f"Unsupported LiteLLM provider: {provider}") from e

        config = ProviderConfigManager.get_provider_chat_config(
            model=model_name, provider=provider_enum)
        if config is None:
            raise RuntimeError(f"No LiteLLM config for provider: {provider}")

        messages = req_map.get("messages", [])
        is_streaming = bool(req_map.get("stream"))
        optional_params = {
            k: v for k, v in req_map.items()
            if k not in {"model", "messages"}
        }

        litellm_params: dict = {}
        is_vertex = provider in ("vertex_ai", "vertex_ai_beta")
        if is_vertex:
            # ADC token comes from the Cloud Run service identity at runtime.
            litellm_params["vertex_project"] = self.gcp_project
            litellm_params["vertex_location"] = self.gcp_region

        default_api_base = (
            f"https://{self.gcp_region}-aiplatform.googleapis.com"
            if is_vertex else _PROVIDER_API_BASE.get(provider)
        )

        # API keys for non-Vertex providers come from env vars set by Cloud
        # Run (Secret Manager-backed). LiteLLM's validate_environment doesn't
        # always read them itself, so pass explicitly.
        api_key = None
        if not is_vertex:
            api_key = (
                os.getenv(f"{provider.upper()}_API_KEY")
                or os.getenv(f"{provider.upper().replace('_AI', '')}_API_KEY")
            )

        headers = config.validate_environment(
            api_key=api_key,
            headers={},
            model=model_name,
            messages=messages,
            optional_params=optional_params,
            api_base=default_api_base,
            litellm_params=litellm_params,
        )

        # Anthropic blocks requests that look browser-originated unless the
        # caller acknowledges direct-browser access via this opt-in header.
        # Required when the LB forwards traffic that originally came from
        # a browser (e.g., the sample UI).
        if provider == "anthropic":
            headers["anthropic-dangerous-direct-browser-access"] = "true"

        # Vertex AI's auth lives on the LLM *handler*, not the config: the
        # config's validate_environment doesn't include the ADC bearer token.
        # Call VertexBase directly to mint the token via ADC and inject it.
        if is_vertex and "Authorization" not in headers and "authorization" not in headers:
            from litellm.llms.vertex_ai.vertex_llm_base import VertexBase
            vb = VertexBase()
            token, _ = vb._ensure_access_token(
                credentials=None,
                project_id=self.gcp_project,
                custom_llm_provider="vertex_ai",
            )
            headers["Authorization"] = f"Bearer {token}"

        if is_vertex:
            # VertexGeminiConfig doesn't override get_complete_url; build the
            # generateContent URL via LiteLLM's internal helper. _get_vertex_url
            # returns (full_url_with_suffix, suffix_only) — use only the first.
            from litellm.llms.vertex_ai.common_utils import _get_vertex_url
            api_base, _ = _get_vertex_url(
                mode="chat",
                model=model_name,
                stream=is_streaming,
                vertex_project=self.gcp_project,
                vertex_location=self.gcp_region,
                vertex_api_version="v1",
            )
        else:
            api_base = config.get_complete_url(
                api_base=default_api_base,
                api_key=None,
                model=model_name,
                optional_params=optional_params,
                stream=is_streaming,
                litellm_params=litellm_params,
            )

        body_dict = self._transform_request_body(
            config, provider, model_name, messages, optional_params,
            litellm_params, headers, api_base,
        )
        return api_base, headers, body_dict, provider, model_name

    @staticmethod
    def _transform_request_body(
        config: Any,
        provider: str,
        model_name: str,
        messages: list,
        optional_params: dict,
        litellm_params: dict,
        headers: dict,
        api_base: str,
    ) -> dict:
        """Call the provider config's body transform.

        Vertex Gemini's `transform_request` raises NotImplementedError because
        LiteLLM puts that provider's body construction on the handler, not the
        config — its sync transform isn't exposed publicly. We fall back to a
        minimal OpenAI→generateContent transform for that one provider.
        """
        try:
            return config.transform_request(
                model=model_name,
                messages=messages,
                optional_params=optional_params,
                litellm_params=litellm_params,
                headers=headers,
            )
        except NotImplementedError:
            if provider not in ("vertex_ai", "vertex_ai_beta"):
                raise
            return _vertex_gemini_body({
                "messages": messages,
                **optional_params,
            })

    def _handle_buffered_chunk(
        self,
        state: _StreamState,
        raw: bytes,
        end_of_stream: bool,
    ) -> service_pb2.BodyResponse:
        state.body_buffer.extend(raw)
        body_resp = service_pb2.BodyResponse()
        if not end_of_stream:
            # Suppress intermediate chunks; we emit the full transformed body
            # once upstream finishes.
            body_resp.response.body_mutation.body = b""
            return body_resp
        try:
            openai_dict = self._transform_response_to_openai(
                state, bytes(state.body_buffer))
            body_resp.response.body_mutation.body = json.dumps(
                openai_dict).encode("utf-8")
        except Exception:
            logging.exception(
                "Response transformation failed; passing through raw body")
            body_resp.response.body_mutation.body = bytes(state.body_buffer)
        return body_resp

    def _transform_response_to_openai(
        self,
        state: _StreamState,
        raw_bytes: bytes,
    ) -> dict:
        """Run the provider response through LiteLLM's response transformer."""
        try:
            provider_enum = LlmProviders(state.provider)
        except ValueError:
            return json.loads(raw_bytes)

        config = ProviderConfigManager.get_provider_chat_config(
            model=state.model, provider=provider_enum)
        if config is None:
            return json.loads(raw_bytes)

        fake_response = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=raw_bytes,
            request=httpx.Request("POST", "https://upstream.invalid"),
        )
        result = config.transform_response(
            model=state.model,
            raw_response=fake_response,
            model_response=ModelResponse(),
            logging_obj=self._stub_logging(state),
            request_data=state.request_body,
            messages=state.request_body.get("messages", []),
            optional_params={},
            litellm_params={},
            encoding=None,
        )
        return result.model_dump()

    def _handle_streaming_chunk(
        self,
        state: _StreamState,
        raw: bytes,
        end_of_stream: bool,
    ) -> service_pb2.BodyResponse:
        """Transform provider SSE chunks to OpenAI SSE chunks via LiteLLM."""
        iterator = self._stream_iterator(state)
        if iterator is None:
            # Provider returns OpenAI-format SSE already — pass-through.
            body_resp = service_pb2.BodyResponse()
            body_resp.response.body_mutation.body = raw
            return body_resp

        # Normalize CRLF to LF; SSE events are delimited by `\n\n`.
        state.sse_buffer += raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
        out = bytearray()
        while "\n\n" in state.sse_buffer:
            event, _, rest = state.sse_buffer.partition("\n\n")
            state.sse_buffer = rest
            data = _extract_sse_data(event)
            if data is None or data == "[DONE]":
                continue
            try:
                chunk_dict = json.loads(data)
            except json.JSONDecodeError:
                logging.debug("Discarding non-JSON SSE event: %r", data[:200])
                continue
            try:
                openai_chunk = iterator.chunk_parser(chunk_dict)
                payload = openai_chunk.model_dump() if hasattr(
                    openai_chunk, "model_dump") else openai_chunk
                out.extend(b"data: ")
                out.extend(json.dumps(payload).encode("utf-8"))
                out.extend(b"\n\n")
            except Exception:
                logging.exception("Streaming chunk parser failed; skipping")
        if end_of_stream:
            out.extend(b"data: [DONE]\n\n")
        body_resp = service_pb2.BodyResponse()
        body_resp.response.body_mutation.body = bytes(out)
        return body_resp

    def _stream_iterator(self, state: _StreamState):
        """Build a per-stream provider chunk iterator.

        Returns None for OpenAI-compatible providers (chunks pass through
        unchanged) and as a graceful fallback when the provider's iterator
        constructor signature can't be satisfied. The iterator instance is
        cached on state because per-chunk parsing maintains internal state
        (tool_index, content_blocks, etc.).
        """
        if state.stream_iterator_resolved:
            return state.stream_iterator
        state.stream_iterator_resolved = True
        if state.provider in ("vertex_ai", "vertex_ai_beta"):
            from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
                ModelResponseIterator,
            )
        elif state.provider == "anthropic":
            from litellm.llms.anthropic.chat.handler import ModelResponseIterator
        else:
            return None
        # The iterator constructor signature drifts across LiteLLM versions —
        # try the known shapes, then fall back to pass-through streaming.
        logging_obj = self._stub_logging(state)
        for kwargs in (
            {"streaming_response": iter([]), "sync_stream": True, "json_mode": False},
            {"streaming_response": iter([]), "sync_stream": True, "logging_obj": logging_obj},
            {"streaming_response": iter([]), "sync_stream": True},
        ):
            try:
                state.stream_iterator = ModelResponseIterator(**kwargs)
                return state.stream_iterator
            except TypeError:
                continue
        logging.warning(
            "Could not construct a streaming chunk iterator for provider %r; "
            "streaming responses will pass through in provider format.",
            state.provider,
        )
        return None

    @staticmethod
    def _stub_logging(state: _StreamState) -> LiteLLMLogging:
        """A no-op LiteLLM Logging object usable by provider transformers."""
        obj = LiteLLMLogging(
            model=state.model or "unknown",
            messages=state.request_body.get("messages", []),
            stream=state.is_streaming,
            call_type="completion",
            start_time=datetime.datetime.now(),
            litellm_call_id="ext-proc-stub",
            function_id="ext-proc-stub",
        )
        if not hasattr(obj, "optional_params"):
            obj.optional_params = {}
        return obj


def _vertex_gemini_body(req_map: dict) -> dict:
    """OpenAI chat-completions body → Vertex AI generateContent body.

    Used as a fallback because LiteLLM's VertexGeminiConfig doesn't expose a
    sync `transform_request` (only async). All other providers go through
    LiteLLM's standard config.transform_request flow.
    """
    contents: list[dict] = []
    system_parts: list[dict] = []
    for msg in req_map.get("messages", []):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "user")
        content = msg.get("content", "")
        text = content if isinstance(content, str) else json.dumps(content)
        if role == "system":
            system_parts.append({"text": text})
        else:
            vertex_role = "model" if role == "assistant" else "user"
            contents.append({"role": vertex_role, "parts": [{"text": text}]})
    body: dict = {"contents": contents}
    if system_parts:
        body["systemInstruction"] = {"parts": system_parts}
    gen_cfg: dict = {}
    for src, dst in (
        ("temperature", "temperature"),
        ("top_p", "topP"),
        ("top_k", "topK"),
        ("max_tokens", "maxOutputTokens"),
        ("max_completion_tokens", "maxOutputTokens"),
        ("stop", "stopSequences"),
        ("presence_penalty", "presencePenalty"),
        ("frequency_penalty", "frequencyPenalty"),
    ):
        if src in req_map and req_map[src] is not None:
            gen_cfg[dst] = req_map[src]
    if gen_cfg:
        body["generationConfig"] = gen_cfg
    return body


def _extract_sse_data(event: str) -> str | None:
    """Extract concatenated `data:` lines from a single SSE event block.

    SSE events can contain `event:`, `id:`, and `:comment` lines that we ignore.
    Returns None if the event has no data line.
    """
    parts: list[str] = []
    for line in event.split("\n"):
        if line.startswith("data:"):
            parts.append(line[len("data:"):].lstrip())
    return "\n".join(parts) if parts else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    LiteLLMGatewayCallout(disable_tls=True).run()
