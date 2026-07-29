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

"""Portkey Gateway callout: sidecar + custom_host loopback adapter.

* The callout receives a vanilla OpenAI request from the LB.
* Sends it to the Portkey sidecar (``localhost:8787``) with
  ``x-portkey-custom-host: http://localhost:9999`` and the provider API key.
* Portkey translates OpenAI -> provider format and POSTs to ``:9999``, where
  the callout's capture server records the translated bytes/headers/path.
* The callout returns the captured provider-native bytes to the LB as ext_proc
  mutations; the LB forwards to the provider Internet NEG selected by the URL
  map's ``header_matches: x-model-id`` (prefix match on the provider segment).
* On the response, the LB delivers the provider-native response back; the
  callout arms ``:9998`` with those bytes, calls Portkey again with
  ``x-portkey-custom-host: http://localhost:9998``, and returns Portkey's
  OpenAI-shaped translation to the LB.

Routing model: the LB's URL map picks the provider backend from the
``x-model-id`` header *before* this callout fires.
The URL map uses a ``prefix_match`` on the provider segment (for example
``anthropic/`` for ``x-model-id: anthropic/claude-...``). This callout never
switches backends; it only mutates the body and headers.

Body handling: the callout requests ``BUFFERED`` body delivery via
``mode_override`` on the request-headers response, but the GCLB Traffic
Extension data plane keeps response bodies STREAMED, so providers that flush
in several pieces (for example OpenRouter's keep-alive padding) arrive as
multiple chunks. ``on_response_body`` therefore buffers chunks (clearing each
from the egress) and translates the reassembled body on the final chunk.
Client streaming (``stream: true``) is explicitly rejected with HTTP 501.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import google.auth
import google.auth.transport.requests
from grpc import ServicerContext

from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import (
    ProcessingMode,
)
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.service import callout_server
from extproc.service import callout_tools
from extproc.example.portkey_gateway import capture_server, portkey_client

# ---------------------------------------------------------------------------
# Provider registry
#
# Maps the ``provider/model`` id's provider prefix onto Portkey's provider
# identifier, the Internet NEG hostname, and the API-key env var name. Add a
# provider here and the rest of the callout picks it up automatically.
# ---------------------------------------------------------------------------


class ProviderSpec(NamedTuple):
    # Value for the x-portkey-provider header.
    portkey_id: str
    # :authority for the LB-forwarded request; may contain "{region}".
    api_base_host: str
    # Env var holding the API key; None for Vertex AI (uses ADC).
    api_key_env: str | None
    # Path prefix to prepend to the path Portkey POSTs to ``custom_host``.
    # Portkey strips each provider's URL prefix when forwarding to custom_host
    # (e.g. "/messages" for Anthropic instead of "/v1/messages"). We add the
    # prefix back so the request the LB forwards reaches the provider's actual
    # endpoint. Vertex AI is special: Portkey emits the full path including
    # the project/region segments, so no prefix is needed there.
    api_path_prefix: str = ""
    # Default for the ``max_tokens`` field when the client omits it. OpenAI
    # clients usually do (the OpenAI API treats it as optional), but
    # Anthropic's Messages API requires it.
    default_max_tokens: int | None = None


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        portkey_id="anthropic",
        api_base_host="api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        api_path_prefix="/v1",        # "/messages" -> "/v1/messages"
        default_max_tokens=4096,
    ),
    "vertex_ai": ProviderSpec(
        portkey_id="vertex-ai",
        api_base_host="{region}-aiplatform.googleapis.com",
        api_key_env=None,
        # Portkey emits the full /v1/projects/... path; no prefix needed.
        api_path_prefix="",
    ),
    "groq": ProviderSpec(
        portkey_id="groq",
        api_base_host="api.groq.com",
        api_key_env="GROQ_API_KEY",
        # "/chat/completions" -> "/openai/v1/chat/completions"
        api_path_prefix="/openai/v1",
    ),
    "openrouter": ProviderSpec(
        portkey_id="openrouter",
        api_base_host="openrouter.ai",
        api_key_env="OPENROUTER_API_KEY",
        # "/v1/chat/completions" -> "/api/v1/chat/completions"
        api_path_prefix="/api",
    ),
}


def detect_provider_from_model(model: str) -> tuple[str, str]:
    """Split a ``provider/model`` id into ``(provider, model_name)``.

    The first ``/`` segment is the provider; the remainder is the model name.
    OpenRouter intentionally keeps its inner ``/`` (e.g.
    ``openrouter/openai/gpt-oss-20b:free`` -> provider ``openrouter``, model
    ``openai/gpt-oss-20b:free``). When no provider prefix is given, defaults
    to ``vertex_ai`` to match the URL map's fallthrough behaviour.
    """
    if "/" in model:
        provider, _, model_name = model.partition("/")
        return provider, model_name
    return "vertex_ai", model


def get_api_key(provider: str) -> str | None:
    """Return the provider's API key env-var value (None for Vertex AI)."""
    spec = PROVIDERS.get(provider)
    if spec is None or spec.api_key_env is None:
        return None
    return os.getenv(spec.api_key_env)


# ---------------------------------------------------------------------------
# Vertex AI ADC bearer-token helper
#
# The Cloud Run service identity supplies Application Default Credentials; we
# mint an access token from those and pass it as ``Authorization: Bearer
# <token>`` to Portkey (with ``x-portkey-provider: vertex-ai``). Portkey
# treats the token as the provider's auth header and forwards it to
# ``aiplatform.googleapis.com``.
#
# The minted token is short-lived. ``mint_adc_token`` refreshes on demand;
# ``google.auth.transport.requests.Request().refresh(creds)`` mutates the
# same ``Credentials`` object in place, so callers can call this every
# request cheaply. (``google.auth`` caches under the hood.)
# ---------------------------------------------------------------------------

_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)


def _load_default_credentials():
    """Indirection so tests can patch the credentials source."""
    creds, _ = google.auth.default(scopes=_SCOPES)
    return creds


def mint_adc_token() -> str:
    """Return a valid ADC access token, refreshing if expired."""
    creds = _load_default_credentials()
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())
    return creds.token


# ---------------------------------------------------------------------------
# Callout constants and implementation
# ---------------------------------------------------------------------------

HEADER_PORTKEY_ROUTED = "x-portkey-routed"
HEADER_PORTKEY_PROVIDER = "x-portkey-provider-stamp"
HEADER_PORTKEY_MODEL = "x-portkey-model-stamp"

# LLM endpoints the callout transforms. Only /v1/* paths are listed: the
# URL map's provider route rules match on the /v1/ prefix, so only these
# paths can reach a provider backend. The Traffic Extension CEL match in
# deploy/terraform/main.tf mirrors this list.
LLM_ENDPOINTS = frozenset({
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/embeddings",
})

_MANAGED_HEADERS = frozenset({
    "host", ":authority", ":path", "content-length", "content-type",
})

# Browser-identifying request headers stripped from LLM requests. The LB
# forwards provider-native requests server-to-server; leaking these upstream
# misrepresents the request, and Anthropic rejects requests carrying an
# Origin header outright ("CORS requests must set
# 'anthropic-dangerous-direct-browser-access'").
_BROWSER_HEADERS = (
    "origin",
    "referer",
    "cookie",
    "sec-fetch-site",
    "sec-fetch-mode",
    "sec-fetch-dest",
    "sec-fetch-user",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
)


@dataclass
class _StreamState:
    is_llm: bool = False
    provider: str | None = None
    correlation: str = ""
    request_body: dict[str, Any] = field(default_factory=dict)
    # Response-body chunks accumulated across STREAMED ext_proc messages.
    response_chunks: list[bytes] = field(default_factory=list)


def _state(context: ServicerContext) -> _StreamState:
    state = getattr(context, "_portkey_state", None)
    if state is None:
        state = _StreamState()
        context._portkey_state = state
    return state


class PortkeyGatewayCallout(callout_server.CalloutServer):
    """ext_proc adapter that uses Portkey-as-sidecar for translation only."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.gcp_project = os.getenv("GCP_PROJECT_ID", "")
        self.gcp_region = os.getenv("GCP_REGION", "us-central1")
        self.portkey_url = os.getenv(
            "PORTKEY_BASE_URL", "http://127.0.0.1:8787")

        self._capture_request_port = int(
            os.getenv("CAPTURE_REQUEST_PORT", "9999"))
        self._capture_response_port = int(
            os.getenv("CAPTURE_RESPONSE_PORT", "9998"))

        # The capture server and Portkey client are spun up lazily on a worker
        # thread because the gRPC server runs on its own thread pool and we
        # need an asyncio event loop to host both.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._capture: capture_server.CaptureServer | None = None
        self._client: portkey_client.PortkeyClient | None = None
        self._start_async_components()

    # ---------------- async runtime in a worker thread ----------------

    def _start_async_components(self) -> None:
        loop_ready = threading.Event()

        def runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._capture = capture_server.CaptureServer(
                request_port=self._capture_request_port,
                response_port=self._capture_response_port,
            )
            self._client = portkey_client.PortkeyClient(
                base_url=self.portkey_url)
            loop.run_until_complete(self._capture.start())
            loop_ready.set()
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(self._capture.stop())
                loop.run_until_complete(self._client.close())
                loop.close()

        threading.Thread(
            target=runner, name="portkey-async", daemon=True).start()
        if not loop_ready.wait(timeout=10):
            raise RuntimeError("async runtime failed to start within 10s")
        if self._capture is None or self._client is None:
            raise RuntimeError("async components missing after loop start")

    def _run_async(self, coro):
        # self._loop is guaranteed non-None once __init__ returns.
        future = asyncio.run_coroutine_threadsafe(
            coro, self._loop)  # type: ignore[arg-type]
        # Timeout so a hung sidecar surfaces as concurrent.futures.TimeoutError
        # rather than hanging the gRPC thread indefinitely.
        return future.result(timeout=30)

    # ---------------- ext_proc phases ----------------

    def on_request_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.ProcessingResponse | None:
        path = ""
        for h in headers.headers.headers:
            if h.key == ":path":
                path = h.raw_value.decode("utf-8")
                break
        if path not in LLM_ENDPOINTS:
            return None
        state = _state(context)
        state.is_llm = True
        state.correlation = uuid.uuid4().hex
        logging.info("Routed LLM request path=%s correlation=%s",
                     path, state.correlation)
        # A full ProcessingResponse (not a HeadersResponse) because
        # mode_override lives on the outer message and Envoy only honors it
        # on the request-headers response. BUFFERED delivery is required:
        # some providers (e.g. OpenRouter) flush response bodies in several
        # chunks, and the translation needs the complete body at once.
        resp = service_pb2.ProcessingResponse()
        resp.request_headers.response.header_mutation.set_headers.append(
            HeaderValueOption(header=HeaderValue(
                key=HEADER_PORTKEY_ROUTED, raw_value=b"true")))
        resp.request_headers.response.header_mutation.remove_headers.extend(
            _BROWSER_HEADERS)
        resp.mode_override.request_body_mode = ProcessingMode.BUFFERED
        resp.mode_override.response_body_mode = ProcessingMode.BUFFERED
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
            logging.warning(
                "Empty request body on LLM endpoint (corr=%s); passing through "
                "unchanged. This is unexpected for /v1/chat/completions etc.",
                state.correlation,
            )
            return service_pb2.BodyResponse()

        try:
            req_map = json.loads(raw)
        except json.JSONDecodeError as e:
            logging.warning("Invalid JSON body: %s", e)
            return callout_tools.header_immediate_response(
                StatusCode.BadRequest)

        if req_map.get("stream"):
            logging.info(
                "Streaming not yet supported by portkey_gateway sample")
            return callout_tools.header_immediate_response(
                StatusCode.NotImplemented)

        model = req_map.get("model")
        if not isinstance(model, str) or not model:
            return callout_tools.header_immediate_response(
                StatusCode.BadRequest)

        provider, model_name = detect_provider_from_model(model)
        spec = PROVIDERS.get(provider)
        if spec is None:
            return callout_tools.header_immediate_response(
                StatusCode.BadRequest)

        state.provider = provider
        state.request_body = dict(req_map, model=model_name)
        if (spec.default_max_tokens is not None
                and "max_tokens" not in state.request_body):
            state.request_body["max_tokens"] = spec.default_max_tokens

        try:
            api_key, extra_headers = self._auth_for(provider)
        except Exception:
            logging.exception("auth setup failed")
            return callout_tools.header_immediate_response(
                StatusCode.InternalServerError)

        if self._capture is None or self._client is None:
            raise RuntimeError("async components not initialized")
        self._capture.arm_request(state.correlation, provider)
        custom_host = f"http://127.0.0.1:{self._capture.request_port}"
        try:
            self._run_async(self._client.translate(
                openai_body=state.request_body,
                provider=spec.portkey_id,
                api_key=api_key,
                custom_host=custom_host,
                correlation=state.correlation,
                extra_headers=extra_headers,
            ))
        except Exception:
            logging.exception("Portkey request-translation call failed")
            self._capture.disarm(state.correlation)
            return callout_tools.header_immediate_response(
                StatusCode.BadGateway)

        try:
            captured = self._capture.take_captured_request(state.correlation)
        except KeyError:
            logging.error(
                "Portkey did not POST to capture server (corr=%s)",
                state.correlation,
            )
            self._capture.disarm(state.correlation)
            return callout_tools.header_immediate_response(
                StatusCode.BadGateway)

        body_resp = service_pb2.BodyResponse()
        body_resp.response.body_mutation.body = captured.body

        authority = spec.api_base_host.format(region=self.gcp_region)
        # Reattach the provider URL prefix Portkey stripped (see ProviderSpec).
        full_path = spec.api_path_prefix + captured.path
        rewrites: list[tuple[str, str]] = [
            (":path", full_path),
            (":authority", authority),
            ("host", authority),
            ("content-type", "application/json"),
            ("content-length", str(len(captured.body))),
            ("accept-encoding", "identity"),
            ("user-agent", "portkey-gateway/1.0"),
            (HEADER_PORTKEY_PROVIDER, spec.portkey_id),
            (HEADER_PORTKEY_MODEL, model_name),
        ]
        for k, v in captured.headers.items():
            kl = k.lower()
            if kl in _MANAGED_HEADERS:
                continue
            if kl.startswith("x-portkey-"):
                continue  # internal; don't leak to the provider
            rewrites.append((kl, v))

        for k, v in rewrites:
            body_resp.response.header_mutation.set_headers.append(
                HeaderValueOption(
                    header=HeaderValue(key=k, raw_value=v.encode("utf-8")),
                    append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
                ))
        return body_resp

    def _auth_for(self, provider: str) -> tuple[str, dict[str, str]]:
        if provider == "vertex_ai":
            if not self.gcp_project:
                logging.warning(
                    "GCP_PROJECT_ID is not set; Vertex AI requests will fail "
                    "upstream with an opaque error. Set GCP_PROJECT_ID on the "
                    "callout container."
                )
            token = mint_adc_token()
            return token, {
                "x-portkey-vertex-project-id": self.gcp_project,
                "x-portkey-vertex-region": self.gcp_region,
            }
        api_key = get_api_key(provider)
        if not api_key:
            raise RuntimeError(f"missing API key for provider {provider}")
        return api_key, {}

    def on_response_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.HeadersResponse | None:
        state = _state(context)
        if not state.is_llm:
            return None
        resp = service_pb2.HeadersResponse()
        # Provider's Content-Length will be wrong after our body transform.
        # Drop it so Envoy switches to chunked transfer encoding. Drop
        # Content-Encoding too: providers may gzip despite our
        # Accept-Encoding: identity, and the body we return is plain JSON,
        # so a stale gzip header would break decoding clients.
        resp.response.header_mutation.remove_headers.append("content-length")
        resp.response.header_mutation.remove_headers.append("content-encoding")
        return resp

    def on_response_body(
        self,
        body: service_pb2.HttpBody,
        context: ServicerContext,
    ) -> service_pb2.BodyResponse | service_pb2.ImmediateResponse | None:
        state = _state(context)
        if not state.is_llm:
            return None
        if not body.end_of_stream:
            # The LB delivers response bodies STREAMED: providers that flush
            # in several pieces (for example OpenRouter's keep-alive padding)
            # arrive as multiple chunks. Buffer each chunk and clear it from
            # the egress; the full body is translated on the final chunk.
            state.response_chunks.append(body.body or b"")
            resp = service_pb2.BodyResponse()
            resp.response.body_mutation.clear_body = True
            return resp

        if state.provider is None:
            logging.error(
                "on_response_body called without provider set (corr=%s)",
                state.correlation,
            )
            return callout_tools.header_immediate_response(
                StatusCode.InternalServerError)

        provider_response = b"".join(state.response_chunks) + (body.body or b"")
        # Some providers (notably Vertex AI) gzip responses even when we ask
        # for ``identity`` via Accept-Encoding. Detect by magic bytes and
        # decompress so Portkey's response transformer sees plain JSON.
        if provider_response[:3] == b"\x1f\x8b\x08":
            try:
                provider_response = gzip.decompress(provider_response)
                logging.info(
                    "decompressed gzipped %s response (corr=%s)",
                    state.provider, state.correlation)
            except Exception:
                logging.exception(
                    "gzip-magic detected but decompress failed (corr=%s)",
                    state.correlation)
        spec = PROVIDERS[state.provider]

        # On any failure below the body passes through untranslated. Earlier
        # chunks were cleared from the egress, so the pass-through response
        # must carry the full reassembled body, not just the final chunk.
        def passthrough() -> service_pb2.BodyResponse:
            resp = service_pb2.BodyResponse()
            resp.response.body_mutation.body = provider_response
            return resp

        try:
            api_key, extra_headers = self._auth_for(state.provider)
        except Exception:
            logging.exception("auth setup failed on response phase")
            # Pass body through on auth failure. We can't safely synthesize
            # an ImmediateResponse here without crashing the framework's
            # response_body wrapper.
            return passthrough()

        if self._capture is None or self._client is None:
            raise RuntimeError("async components not initialized")

        self._capture.arm_response(state.correlation, provider_response)
        custom_host = f"http://127.0.0.1:{self._capture.response_port}"
        try:
            portkey_resp = self._run_async(self._client.translate(
                openai_body=state.request_body,
                provider=spec.portkey_id,
                api_key=api_key,
                custom_host=custom_host,
                correlation=state.correlation,
                extra_headers=extra_headers,
            ))
        except Exception:
            logging.exception("Portkey response-translation call failed; "
                              "passing provider body through unchanged")
            self._capture.disarm(state.correlation)
            return passthrough()

        if portkey_resp.status_code != 200:
            logging.error(
                "Portkey response translation status %s; passing provider "
                "body through unchanged. Portkey error body: %s",
                portkey_resp.status_code, portkey_resp.text[:500])
            self._capture.disarm(state.correlation)
            return passthrough()

        new_body = portkey_resp.content
        body_resp = service_pb2.BodyResponse()
        body_resp.response.body_mutation.body = new_body
        body_resp.response.header_mutation.set_headers.append(
            HeaderValueOption(
                header=HeaderValue(
                    key="content-length",
                    raw_value=str(len(new_body)).encode("utf-8"),
                ),
                append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
            ))
        return body_resp


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    PortkeyGatewayCallout(disable_tls=True).run()
