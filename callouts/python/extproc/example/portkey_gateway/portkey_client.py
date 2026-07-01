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

A single ``translate`` method drives both phases of the loopback. Portkey
does the same round-trip both times: translate the OpenAI body to provider
format, POST to ``custom_host``, translate the response back to OpenAI,
return it. Which loopback endpoint we point ``custom_host`` at decides
what the caller does with the result.

* **Request phase**: ``custom_host = http://127.0.0.1:9999`` (capture
  server). We discard the response Portkey returns (the translated stub)
  and use the bytes the capture endpoint recorded instead.

* **Response phase**: ``custom_host = http://127.0.0.1:9998`` (replay
  server). The replay endpoint serves the LB-captured provider bytes;
  Portkey translates them back to OpenAI and returns that to us.

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
                 timeout: float = 30.0) -> None:
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
        the appropriate loopback endpoint for the current phase."""
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
