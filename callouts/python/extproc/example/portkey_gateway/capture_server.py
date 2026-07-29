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

"""Localhost HTTP server for the Portkey ``custom_host`` loopback.

Two endpoints, both running in-process on the callout container:

* **request port (``:9999``)**: Portkey POSTs the translated provider-native
  request here. We record body + headers + path against a correlation id, then
  return a stub response (so Portkey does not error parsing it).

* **response port (``:9998``)**: when the LB sends the provider's response back
  through the callout's response phase, we arm this endpoint with the captured
  bytes; the callout then makes a second Portkey call with
  ``x-portkey-custom-host`` pointing here, and Portkey reads our armed bytes as
  if they were a real upstream response, runs its translator, and returns OpenAI
  format.

Correlation id (``X-Portkey-Callout-Correlation``) ties the two phases together
so concurrent requests do not cross-contaminate. The callout generates the id
(uuid4) and forwards it through Portkey via ``x-portkey-forward-headers``.

The endpoints bind to 127.0.0.1 only. They are reachable only from inside the
same Cloud Run pod (the Portkey sidecar shares the network namespace) and never
from external traffic.
"""

from __future__ import annotations

import json
from typing import NamedTuple

from aiohttp import web

# ---------------------------------------------------------------------------
# Provider response stubs for the request-capture loopback
#
# When the callout uses the ``x-portkey-custom-host`` loopback to extract
# provider-native request bytes from Portkey, the local capture endpoint
# (``:9999``) has to return *something*: Portkey will try to parse it as the
# provider's native response and translate it to OpenAI format. We discard that
# translated reply (we only wanted the captured request); but Portkey must not
# error parsing the stub, or it will fail the whole call.
#
# Each stub here is the minimum response shape that satisfies the corresponding
# Portkey response transformer.
# ---------------------------------------------------------------------------

_STUBS: dict[str, dict] = {
    "anthropic": {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": "claude-stub",
        "content": [{"type": "text", "text": ""}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    },
    "vertex_ai": {
        "candidates": [{
            "content": {"role": "model", "parts": [{"text": ""}]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {
            "promptTokenCount": 0,
            "candidatesTokenCount": 0,
            "totalTokenCount": 0,
        },
    },
    "groq": {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": "groq-stub",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": ""},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    },
    "openrouter": {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": "openrouter-stub",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": ""},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    },
}


# Providers the stub generator knows about; derived from _STUBS so the two
# can never drift apart.
REQUEST_CAPTURE_PROVIDERS = tuple(_STUBS)


def build_stub_response(provider: str) -> bytes:
    """Return the JSON-encoded stub body for ``provider``.

    Raises ``KeyError`` for unknown providers. Callers should validate against
    ``REQUEST_CAPTURE_PROVIDERS`` first.
    """
    return json.dumps(_STUBS[provider]).encode("utf-8")


# ---------------------------------------------------------------------------
# Capture server
# ---------------------------------------------------------------------------

# Correlation header contract shared with portkey_client (which forwards it
# through Portkey via x-portkey-forward-headers).
CORRELATION_HEADER = "x-portkey-callout-correlation"


class CapturedRequest(NamedTuple):
    path: str
    headers: dict[str, str]
    body: bytes


class CaptureServer:
    """Runs the :9999 and :9998 HTTP listeners with per-correlation state.

    Pass ``request_port=0`` / ``response_port=0`` to let the OS pick an
    ephemeral port (useful in tests). After ``start()`` the actual bound ports
    are available as ``request_port`` / ``response_port`` attributes.
    """

    def __init__(self, request_port: int = 9999,
                 response_port: int = 9998) -> None:
        self._req_configured = request_port
        self._rsp_configured = response_port
        self._req_runner: web.AppRunner | None = None
        self._rsp_runner: web.AppRunner | None = None
        self._armed_request: dict[str, str] = {}      # corr -> provider
        self._captured: dict[str, CapturedRequest] = {}
        self._armed_response: dict[str, bytes] = {}   # corr -> response bytes

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        req_app = web.Application()
        req_app.router.add_route("*", "/{tail:.*}", self._on_request_capture)
        self._req_runner = web.AppRunner(req_app)
        await self._req_runner.setup()
        req_site = web.TCPSite(
            self._req_runner, "127.0.0.1", self._req_configured)
        await req_site.start()
        # _server may be None on some aiohttp versions until the site is
        # started; by this point start() has completed, so sockets are bound.
        self.request_port = (
            req_site._server.sockets[0]  # type: ignore[union-attr]
            .getsockname()[1])

        rsp_app = web.Application()
        rsp_app.router.add_route("*", "/{tail:.*}", self._on_response_replay)
        self._rsp_runner = web.AppRunner(rsp_app)
        await self._rsp_runner.setup()
        rsp_site = web.TCPSite(
            self._rsp_runner, "127.0.0.1", self._rsp_configured)
        await rsp_site.start()
        self.response_port = (
            rsp_site._server.sockets[0]  # type: ignore[union-attr]
            .getsockname()[1])

    async def stop(self) -> None:
        if self._req_runner is not None:
            await self._req_runner.cleanup()
        if self._rsp_runner is not None:
            await self._rsp_runner.cleanup()

    # -- public arming / extraction API ------------------------------------

    def arm_request(self, correlation: str, provider: str) -> None:
        self._armed_request[correlation] = provider

    def take_captured_request(self, correlation: str) -> CapturedRequest:
        return self._captured.pop(correlation)

    def arm_response(self, correlation: str, body: bytes) -> None:
        self._armed_response[correlation] = body

    def disarm(self, correlation: str) -> None:
        """Drop any pending state for ``correlation``.

        Called by the callout on error paths (Portkey call failed, capture
        never happened) so abandoned correlations do not accumulate in a
        long-running server.
        """
        self._armed_request.pop(correlation, None)
        self._captured.pop(correlation, None)
        self._armed_response.pop(correlation, None)

    # -- handlers ----------------------------------------------------------

    async def _on_request_capture(self, request: web.Request) -> web.Response:
        corr = request.headers.get(CORRELATION_HEADER)
        if corr is None or corr not in self._armed_request:
            return web.Response(status=400, text="missing/unknown correlation")
        provider = self._armed_request.pop(corr)
        body = await request.read()
        self._captured[corr] = CapturedRequest(
            path=request.path_qs,
            headers={k.lower(): v for k, v in request.headers.items()},
            body=body,
        )
        return web.Response(
            status=200,
            body=build_stub_response(provider),
            content_type="application/json",
        )

    async def _on_response_replay(self, request: web.Request) -> web.Response:
        corr = request.headers.get(CORRELATION_HEADER)
        if corr is None or corr not in self._armed_response:
            return web.Response(status=400, text="missing/unknown correlation")
        body = self._armed_response.pop(corr)
        return web.Response(
            status=200, body=body, content_type="application/json")
