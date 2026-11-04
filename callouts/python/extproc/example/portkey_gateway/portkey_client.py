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

"""Async HTTP client for the Portkey gateway sidecar.

One ``translate`` call covers both ext_proc phases. Portkey translates the
OpenAI body to provider format, POSTs it to ``custom_host`` (the capture
server), and blocks there until the capture server writes a response. The
callout reads the translated request as soon as it is captured, and only
supplies the response later, once the provider has answered through the LB.
The call therefore stays open across the request and response phases, and
resolves with Portkey's OpenAI-shaped translation of the real response.

Because a single call spans the whole upstream round-trip, ``timeout`` must
exceed the LB backend timeout (``timeout_sec`` in deploy/terraform/main.tf).

We force ``stream=false`` on the round-trip: we only need translated bytes
from Portkey, not a streamed response.
"""

from __future__ import annotations

import json

import httpx

from extproc.example.portkey_gateway.capture_server import CORRELATION_HEADER


_FORWARD_HEADER = "x-portkey-forward-headers"


class PortkeyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8787",
                 timeout: float = 300.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def translate(
        self,
        *,
        openai_body: dict,
        provider: str,
        api_key: str,
        custom_host: str,
        correlation: str,
        extra_headers: dict[str, str],
    ) -> httpx.Response:
        """POST the OpenAI body to Portkey with ``custom_host`` pointing at
        the capture server. Resolves once the capture server unparks."""
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
            "x-portkey-provider": provider,
            "x-portkey-custom-host": custom_host,
            CORRELATION_HEADER: correlation,
            # Ensure Portkey forwards our correlation header (and any caller-
            # supplied extras) through to the custom_host so the capture server
            # can match phases.
            _FORWARD_HEADER: ",".join(
                sorted({CORRELATION_HEADER, *extra_headers.keys()})),
            **extra_headers,
        }
        body = dict(openai_body, stream=False)
        return await self._client.post(
            "/v1/chat/completions",
            content=json.dumps(body),
            headers=headers,
        )
