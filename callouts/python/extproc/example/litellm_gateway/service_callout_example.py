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

"""LiteLLM Gateway callout: a pure ext_proc adapter.

The callout is intentionally thin: it inspects the path, hands the OpenAI body
to LiteLLM for translation (auth, body transform, target URL), and applies the
result as ext_proc header + body mutations. The Cloud Load Balancer then
forwards the rewritten request to the provider via an Internet NEG backend.

Routing model: the LB's URL map picks the provider backend from the client's
`x-model-id` header (prefix-matched on the LiteLLM model id),
*before* this callout fires. GCP Service
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
import uuid
from dataclasses import dataclass, field
from typing import Any, NamedTuple
from urllib.parse import urlsplit

import httpx
from grpc import ServicerContext

import litellm
from litellm import ModelResponse
from litellm.litellm_core_utils.litellm_logging import Logging as LiteLLMLogging
from litellm.types.utils import LlmProviders
from litellm.utils import ProviderConfigManager

from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import (
    ProcessingMode,
)
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.service import callout_server
from extproc.service import callout_tools
from extproc.example.litellm_gateway import gateway_config
from extproc.example.litellm_gateway import quota
from extproc.example.litellm_gateway import routing
from extproc.example.litellm_gateway import telemetry


# Provenance headers stamped on the forwarded request. Observability only;
# they don't affect routing (the LB already routed on the client's
# x-model-id header before this callout ran).
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

# Headers the callout manages itself; never copy these from LiteLLM's output.
_MANAGED_HEADERS = frozenset({
    "host", ":authority", ":path", "content-length", "content-type",
})

# gen_ai.operation.name per endpoint path.
_OPERATIONS = {
    "/v1/chat/completions": "chat",
    "/chat/completions": "chat",
    "/v1/completions": "text_completion",
    "/completions": "text_completion",
    "/v1/embeddings": "embeddings",
    "/embeddings": "embeddings",
}

# Quota reject HTTP status codes mapped to Envoy StatusCode values.
_QUOTA_STATUS = {
    401: StatusCode.Unauthorized,
    402: StatusCode.PaymentRequired,
    403: StatusCode.Forbidden,
    429: StatusCode.TooManyRequests,
    503: StatusCode.ServiceUnavailable,
}

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
}

class _ProviderRequest(NamedTuple):
    api_base_url: str
    headers: dict[str, str]
    body: dict[str, Any]
    provider: str
    model: str

@dataclass
class _StreamState:
    is_llm: bool = False
    is_streaming: bool = False
    model: str = ""
    quota_model: str = ""
    provider: str = ""
    request_body: dict = field(default_factory=dict)
    body_buffer: bytearray = field(default_factory=bytearray)
    sse_buffer: str = ""
    stream_iterator: Any = None
    stream_iterator_resolved: bool = False
    span: Any = None
    api_key: str = ""
    usage: dict = field(default_factory=dict)
    route_mode: bool = False
    model_id_header: str = ""
    call_id: str = ""
    operation: str = "chat"
    upstream_status: int = 200


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
        gateway_config.load()
        routing.configure(gateway_config.routing_settings())
        telemetry.init_tracer()
        quota.init_client()

    def process(
        self,
        callout: service_pb2.ProcessingRequest,
        context: ServicerContext,
    ) -> service_pb2.ProcessingResponse:
        """Set response_body_mode on the response_headers reply.

        On the response_headers event we tell the LB how to deliver the
        response body to us: STREAMED for SSE (so we can transform chunks
        on the fly), BUFFERED for everything else (so the response body
        arrives whole and we can run LiteLLM's transform_response over it).
        """
        if callout.HasField("request_headers"):
            state = _state(context)
            state.route_mode = self._is_route_mode(callout)
        resp = super().process(callout, context)
        if resp.HasField("immediate_response"):
            return resp
        if callout.HasField("response_headers"):
            state = _state(context)
            mode = ProcessingMode()
            mode.response_body_mode = (
                ProcessingMode.STREAMED
                if state.is_streaming else ProcessingMode.BUFFERED
            )
            resp.mode_override.CopyFrom(mode)
        return resp

    # ------------------------------------------------------------------ phases

    def on_request_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.ProcessingResponse | None:
        state = _state(context)
        if state.route_mode:
            header_map = {
                h.key: h.raw_value.decode("utf-8")
                for h in headers.headers.headers
            }
            rewrites = routing.compute_route(header_map)
            if rewrites:
                logging.info(
                    "Route extension rewrite: %s=%r -> %r",
                    routing.ROUTING_HEADER,
                    header_map.get(routing.ROUTING_HEADER),
                    rewrites.get(routing.ROUTING_HEADER),
                )
            else:
                logging.info(
                    "Route extension: no rewrite for %s=%r",
                    routing.ROUTING_HEADER,
                    header_map.get(routing.ROUTING_HEADER),
                )
            resp = service_pb2.ProcessingResponse()
            cr = resp.request_headers.response
            cr.clear_route_cache = True
            for k, v in rewrites.items():
                cr.header_mutation.set_headers.append(
                    HeaderValueOption(
                        header=HeaderValue(
                            key=k, raw_value=v.encode("utf-8")),
                        append_action=(
                            HeaderValueOption
                            .OVERWRITE_IF_EXISTS_OR_ADD)))
            return resp

        path, method = "", ""
        for h in headers.headers.headers:
            if h.key == ":path":
                path = h.raw_value.decode("utf-8")
            elif h.key == ":method":
                method = h.raw_value.decode("utf-8")
        logging.info("Request %s %s", method, path)

        if path not in LLM_ENDPOINTS:
            return None

        state.is_llm = True

        header_map = {
            h.key: h.raw_value.decode("utf-8")
            for h in headers.headers.headers
        }
        auth = header_map.get("authorization", "")
        if auth.lower().startswith("bearer "):
            state.api_key = auth[len("bearer "):].strip()
        state.model_id_header = header_map.get(routing.ROUTING_HEADER, "")
        state.call_id = str(uuid.uuid4())
        state.operation = _OPERATIONS.get(path, "chat")
        disabled = {
            c.strip().lower()
            for c in header_map.get(
                "x-litellm-disable-callbacks", "").split(",")
            if c.strip()
        }
        if "otel" not in disabled:
            state.span = telemetry.start_request_span(header_map)

        resp = service_pb2.ProcessingResponse()
        resp.request_headers.response.header_mutation.set_headers.append(
            HeaderValueOption(
                header=HeaderValue(
                    key=HEADER_LITELLM_ROUTED, raw_value=b"true")))

        return resp

    def on_request_body(
        self,
        body: service_pb2.HttpBody,
        context: ServicerContext,
    ) -> service_pb2.BodyResponse | service_pb2.ImmediateResponse | None:
        # Assumes BUFFERED request body mode: the traffic extension does not
        # set a streamed request body mode, so the load balancer delivers the
        # whole request body in a single REQUEST_BODY message. We rely on that
        # to `json.loads(body.body)` and transform the payload in one pass.
        # If the request body were streamed, this method would receive partial
        # chunks and the JSON parse below would fail on all but the last.
        state = _state(context)
        if not state.is_llm:
            return None

        raw = body.body
        if not raw:
            logging.warning(
                "Empty request body on LLM endpoint; expected a JSON payload.")
            return service_pb2.BodyResponse()

        try:
            req_map = json.loads(raw)
        except json.JSONDecodeError as e:
            logging.warning("Invalid JSON body: %s", e)
            self._end_span(state, 400)
            return callout_tools.header_immediate_response(
                StatusCode.BadRequest)

        model = req_map.get("model")
        if not isinstance(model, str) or not model:
            logging.warning("Request missing 'model' field")
            self._end_span(state, 400)
            return callout_tools.header_immediate_response(
                StatusCode.BadRequest)

        header_model = state.model_id_header
        if (routing.enabled() and header_model and header_model != model
                and header_model.startswith(routing.PROVIDER_PREFIXES)):
            # Routing is enabled (router_settings feature flag), so the URL
            # map routed on an x-model-id the route extension may have
            # rewritten: the header names the model this backend was chosen
            # for. Make it authoritative over the body copy. With routing
            # disabled, the body model always wins (original gateway
            # behavior).
            logging.info(
                "x-model-id overrides body model: %r -> %r",
                model, header_model)
            model = header_model
            req_map["model"] = header_model

        decision = quota.check(state.api_key, model)
        if not decision.allowed:
            logging.info(
                "Quota reject (%s): %s", decision.status, decision.reason)
            self._end_span(state, decision.status)
            return callout_tools.header_immediate_response(
                _QUOTA_STATUS.get(
                    decision.status, StatusCode.TooManyRequests))

        try:
            pr = self._build_provider_request(model, req_map)
        except Exception:
            logging.exception("LiteLLM request transformation failed")
            self._end_span(state, 500)
            return callout_tools.header_immediate_response(
                StatusCode.InternalServerError)

        # state.model is the provider-stripped id (pr.model) for provenance
        # headers/telemetry. state.quota_model is the full LiteLLM id that
        # quota.check() metered above (post header-override), so record()
        # on the response leg writes the same per-model spend counter that
        # check() reads.
        state.model = pr.model
        state.quota_model = model
        state.provider = pr.provider
        state.is_streaming = bool(req_map.get("stream"))
        state.request_body = req_map

        new_body = json.dumps(pr.body).encode("utf-8")

        parsed_url = urlsplit(pr.api_base_url)
        target_authority = parsed_url.netloc
        target_path = parsed_url.path or "/"
        if parsed_url.query:
            target_path = f"{target_path}?{parsed_url.query}"

        logging.info(
            "Routing :authority=%s :path=%s (provider=%s, streaming=%s)",
            target_authority, target_path, pr.provider, state.is_streaming,
        )

        body_resp = service_pb2.BodyResponse()
        body_resp.response.body_mutation.body = new_body

        rewrites: list[tuple[str, str]] = [
            (":path", target_path),
            (":authority", target_authority),
            ("host", target_authority),
            ("content-type", "application/json"),
            ("content-length", str(len(new_body))),
            # Prevent gzip so the response transform sees raw JSON bytes.
            ("accept-encoding", "identity"),
            # Some upstreams (Groq via Cloudflare) reject requests with no
            # User-Agent (or a generic "Google-LB" UA) as bot traffic.
            ("user-agent", "litellm-gateway/1.0"),
            # Provenance markers (observability only, not routing).
            (HEADER_LITELLM_PROVIDER, pr.provider),
            (HEADER_LITELLM_MODEL, pr.model),
            (HEADER_LITELLM_STREAMING,
             "true" if state.is_streaming else "false"),
        ]
        # Apply the auth + provider-specific headers LiteLLM computed
        # (Authorization: Bearer <ADC token>, x-api-key, anthropic-version, …).
        for k, v in pr.headers.items():
            if k.lower() in _MANAGED_HEADERS:
                continue
            rewrites.append((k.lower(), v))

        for k, v in rewrites:
            body_resp.response.header_mutation.set_headers.append(
                HeaderValueOption(
                    header=HeaderValue(key=k, raw_value=v.encode("utf-8")),
                    append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
                ))

        # We don't set clear_route_cache here. GCP traffic extensions can't
        # switch backends after URL map evaluation; routing was already
        # decided by the URL map's header_matches on x-model-id.
        return body_resp

    def on_response_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.HeadersResponse | None:
        state = _state(context)
        if not state.is_llm:
            return service_pb2.HeadersResponse()
        for h in headers.headers.headers:
            if h.key == ":status":
                try:
                    state.upstream_status = int(
                        h.raw_value.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    state.upstream_status = 200
                break
        resp = service_pb2.HeadersResponse()
        # Provider's Content-Length will be wrong after our body transform.
        # Drop it so Envoy switches to chunked transfer encoding.
        resp.response.header_mutation.remove_headers.append("content-length")
        # Usage headers reflect spend recorded so far, so on a streaming
        # response they lag the in-flight request itself (LiteLLM Proxy
        # has the same limitation). Keyless or unknown-key requests get {}
        # here, so only x-litellm-call-id is added below.
        extra = quota.usage_headers(state.api_key)
        if state.call_id:
            extra["x-litellm-call-id"] = state.call_id
        for k, v in extra.items():
            resp.response.header_mutation.set_headers.append(
                HeaderValueOption(
                    header=HeaderValue(key=k, raw_value=v.encode("utf-8")),
                    append_action=(
                        HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD)))
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
            resp = self._handle_streaming_chunk(
                state, body.body or b"", body.end_of_stream)
        else:
            resp = self._handle_buffered_chunk(
                state, body.body or b"", body.end_of_stream)
        if body.end_of_stream:
            u = state.usage
            if state.span is not None:
                telemetry.end_request_span(
                    state.span,
                    provider=state.provider,
                    model=state.model,
                    prompt_tokens=u.get("prompt_tokens"),
                    completion_tokens=u.get("completion_tokens"),
                    total_tokens=u.get("total_tokens"),
                    status=state.upstream_status,
                    streaming=state.is_streaming,
                    operation=state.operation,
                    api_key=state.api_key,
                    call_id=state.call_id)
                state.span = None
            total = u.get("total_tokens")
            if total:
                quota.record(state.api_key, state.quota_model, int(total))
        return resp

    # ---------------------------------------------------------- telemetry

    def _end_span(self, state: "_StreamState", status: int) -> None:
        """End the request span with an error status and clear it."""
        telemetry.end_request_span(
            state.span,
            provider=state.provider,
            model=state.model,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            status=status,
            streaming=state.is_streaming,
            operation=state.operation,
            api_key=state.api_key,
            call_id=state.call_id)
        state.span = None

    @staticmethod
    def _is_route_mode(
        callout: service_pb2.ProcessingRequest,
    ) -> bool:
        """True when invoked as the route extension (mode=route metadata).

        GCP surfaces per-extension metadata in
        metadata_context.filter_metadata, keyed by extension name. This
        reads the `mode` field of each Struct value and matches "route",
        the value deploy/terraform-regional/main.tf sets on the route
        extension's `metadata` block.
        """
        try:
            fm = callout.metadata_context.filter_metadata
            for value in fm.values():
                if value.fields.get("mode") and (
                        value.fields["mode"].string_value == "route"):
                    return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------- LiteLLM

    def _build_provider_request(
        self,
        model: str,
        req_map: dict,
    ) -> _ProviderRequest:
        """Drive LiteLLM provider config to produce the upstream request.

        Returns a `_ProviderRequest` carrying api_base_url, headers, body,
        provider, and model.
        """
        model_name, provider, _, _ = litellm.get_llm_provider(model=model)

        try:
            provider_enum = LlmProviders(provider)
        except ValueError as e:
            raise RuntimeError(
                f"Unsupported LiteLLM provider: {provider}") from e

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
            if not self.gcp_project:
                logging.warning(
                    "Vertex AI request received but GCP_PROJECT_ID is unset; "
                    "downstream call will likely fail with a malformed URL.")
            # ADC token comes from the Cloud Run service identity at runtime.
            litellm_params["vertex_project"] = self.gcp_project
            litellm_params["vertex_location"] = self.gcp_region

        default_api_base_url = (
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
            api_base=default_api_base_url,
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
        if (is_vertex and "Authorization" not in headers
                and "authorization" not in headers):
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
            # returns (full_url_with_suffix, suffix_only); use only the first.
            from litellm.llms.vertex_ai.common_utils import _get_vertex_url
            api_base_url, _ = _get_vertex_url(
                mode="chat",
                model=model_name,
                stream=is_streaming,
                vertex_project=self.gcp_project,
                vertex_location=self.gcp_region,
                vertex_api_version="v1",
            )
        else:
            api_base_url = config.get_complete_url(
                api_base=default_api_base_url,
                api_key=None,
                model=model_name,
                optional_params=optional_params,
                stream=is_streaming,
                litellm_params=litellm_params,
            )

        body_dict = self._transform_request_body(
            config, provider, model_name, messages, optional_params,
            litellm_params, headers,
        )
        return _ProviderRequest(
            api_base_url=api_base_url,
            headers=headers,
            body=body_dict,
            provider=provider,
            model=model_name,
        )

    @staticmethod
    def _transform_request_body(
        config: Any,
        provider: str,
        model_name: str,
        messages: list,
        optional_params: dict,
        litellm_params: dict,
        headers: dict,
    ) -> dict:
        """Call the provider config's body transform.

        Vertex Gemini's `transform_request` raises NotImplementedError because
        LiteLLM puts that provider's body construction on the handler, not the
        config, and its sync transform isn't exposed publicly. We fall back to a
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
            state.usage = openai_dict.get("usage") or {}
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

    @staticmethod
    def _merge_stream_usage(
        state: _StreamState,
        usage: dict,
    ) -> None:
        """Accumulate token usage across streaming SSE events.

        Some providers (e.g. Anthropic) split usage across multiple
        events: an early event reports prompt_tokens, and a later
        event reports completion_tokens alongside a zero placeholder
        for prompt_tokens. A naive overwrite-merge would let the
        placeholder clobber the real prompt count, so this takes the
        max seen so far per field and derives total_tokens from the
        accumulated parts instead of trusting any single event's
        total.
        """
        for k in ("prompt_tokens", "completion_tokens"):
            v = usage.get(k)
            if v:
                state.usage[k] = max(state.usage.get(k, 0), v)
        reported_total = usage.get("total_tokens")
        derived_total = (state.usage.get("prompt_tokens", 0)
                          + state.usage.get("completion_tokens", 0))
        state.usage["total_tokens"] = max(
            derived_total, reported_total or 0,
            state.usage.get("total_tokens", 0))

    def _handle_streaming_chunk(
        self,
        state: _StreamState,
        raw: bytes,
        end_of_stream: bool,
    ) -> service_pb2.BodyResponse:
        """Transform provider SSE chunks to OpenAI SSE chunks via LiteLLM."""
        iterator = self._stream_iterator(state)
        if iterator is None:
            # Provider returns OpenAI-format SSE already; pass it through.
            body_resp = service_pb2.BodyResponse()
            body_resp.response.body_mutation.body = raw
            return body_resp

        # Normalize CRLF to LF; SSE events are delimited by `\n\n`.
        state.sse_buffer += raw.decode(
            "utf-8", errors="replace").replace("\r\n", "\n")
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
                # Opportunistic usage capture: some providers (e.g. Anthropic
                # via message_delta) surface token usage on the final chunk.
                # Merge it into state so on_response_body can meter it the
                # same way as a buffered response. Providers that never
                # include usage in the stream (many OpenAI-compatible ones,
                # absent `stream_options: {include_usage: true}`) are not
                # token-metered on streaming responses; RPM limits still
                # apply since those are enforced on the request leg.
                if isinstance(payload, dict):
                    usage = payload.get("usage")
                    if usage:
                        self._merge_stream_usage(state, usage)
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
            from litellm.llms.vertex_ai.gemini import (
                vertex_and_google_ai_studio_gemini as vertex_gemini,
            )
            ModelResponseIterator = (
                vertex_gemini.ModelResponseIterator)
        elif state.provider == "anthropic":
            from litellm.llms.anthropic.chat.handler import (
                ModelResponseIterator,
            )
        else:
            return None
        # The iterator constructor signature drifts across LiteLLM versions;
        # try the known shapes, then fall back to pass-through streaming.
        logging_obj = self._stub_logging(state)
        for kwargs in (
            {"streaming_response": iter([]), "sync_stream": True,
             "json_mode": False},
            {"streaming_response": iter([]), "sync_stream": True,
             "logging_obj": logging_obj},
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
