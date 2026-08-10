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

Portkey is configured to treat this server as the provider endpoint. A single
port serves both ext_proc phases by *parking* the connection:

1. Portkey POSTs the translated provider-native request here. The server
   records the path, headers, and body, then holds the connection open
   without writing a response.
2. The callout takes the recorded bytes and returns them to the LB, which
   forwards them to the real provider.
3. When the provider's response reaches the callout's response phase, the
   callout hands those bytes to this server, which finally writes them as the
   response on the parked connection.
4. Portkey reads that response and translates it back to OpenAI format.

Parking matters because Portkey sees one ordinary request/response exchange
on one connection, exactly as it would when calling a real provider. The
callout therefore makes no assumptions about whether Portkey keeps state
between a request and its response.

Correlation id (``X-Portkey-Callout-Correlation``) ties a parked connection to
its ext_proc stream so concurrent requests do not cross-contaminate. The
callout generates the id (uuid4) and forwards it through Portkey via
``x-portkey-forward-headers``.

The endpoint binds to 127.0.0.1 only. It is reachable only from inside the
same Cloud Run pod (the Portkey sidecar shares the network namespace) and
never from external traffic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import NamedTuple

from aiohttp import web

# Correlation header contract shared with portkey_client (which forwards it
# through Portkey via x-portkey-forward-headers).
CORRELATION_HEADER = "x-portkey-callout-correlation"

# Upper bound on how long a connection stays parked. It must exceed the LB
# backend timeout (see timeout_sec in deploy/terraform/main.tf) so that a slow
# provider does not trip this first.
DEFAULT_PARK_TIMEOUT = 300.0


class CapturedRequest(NamedTuple):
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class _Pending:
    """State for one in-flight correlation."""
    captured: CapturedRequest | None = None
    captured_event: asyncio.Event = field(default_factory=asyncio.Event)
    response: bytes | None = None
    response_event: asyncio.Event = field(default_factory=asyncio.Event)


class CaptureServer:
    """Serves the Portkey ``custom_host`` loopback on a single port.

    Pass ``port=0`` to let the OS pick an ephemeral port (useful in tests).
    After ``start()`` the actual bound port is available as ``port``.

    Every public coroutine is intended to be scheduled onto the server's own
    event loop (the callout does this through ``_run_async``), so the
    ``asyncio.Event`` objects are only ever touched from that loop.
    """

    def __init__(self, port: int = 9999,
                 park_timeout: float = DEFAULT_PARK_TIMEOUT) -> None:
        self._configured_port = port
        self._park_timeout = park_timeout
        self._runner: web.AppRunner | None = None
        self._pending: dict[str, _Pending] = {}
        self.port = port

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._on_capture)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self._configured_port)
        await site.start()
        # _server may be None on some aiohttp versions until the site is
        # started; by this point start() has completed, so sockets are bound.
        self.port = (
            site._server.sockets[0]  # type: ignore[union-attr]
            .getsockname()[1])

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    # -- public API --------------------------------------------------------

    async def arm(self, correlation: str) -> None:
        """Register ``correlation`` before triggering the Portkey call."""
        self._pending[correlation] = _Pending()

    async def wait_for_capture(self, correlation: str,
                               timeout: float) -> CapturedRequest:
        """Wait until Portkey POSTs the translated request.

        Raises ``KeyError`` if the correlation was never armed,
        ``asyncio.TimeoutError`` if Portkey does not call within ``timeout``,
        and ``RuntimeError`` if the Portkey call failed before capturing
        anything (see ``fail``).
        """
        pending = self._pending[correlation]
        await asyncio.wait_for(pending.captured_event.wait(), timeout)
        if pending.captured is None:
            raise RuntimeError("Portkey call failed before capture")
        return pending.captured

    async def fail(self, correlation: str) -> None:
        """Wake a ``wait_for_capture`` waiter without a captured request.

        The callout calls this when the Portkey call completes without
        POSTing here, whether it raised or returned its own error response,
        so the waiter reports the real cause immediately instead of sitting
        out the capture timeout. A no-op once a capture has happened.
        """
        pending = self._pending.get(correlation)
        if pending is None:
            return
        pending.captured_event.set()

    async def provide_response(self, correlation: str, body: bytes) -> None:
        """Supply the provider's native response, unparking the connection."""
        pending = self._pending.get(correlation)
        if pending is None:
            return
        pending.response = body
        pending.response_event.set()

    async def disarm(self, correlation: str) -> None:
        """Drop state for ``correlation`` and release any parked connection.

        Called by the callout on error paths so abandoned correlations do not
        accumulate, and so a parked handler does not wait out the full park
        timeout when the callout already knows no response is coming.

        Dropping the entry here also covers the case where Portkey never
        called at all, so no handler will ever run to clean it up. A handler
        that is parked holds its own reference to the state, so removing it
        from the map does not disturb it.
        """
        pending = self._pending.pop(correlation, None)
        if pending is None:
            return
        # Leave response as None so the parked handler returns an error.
        pending.response_event.set()

    # -- handler -----------------------------------------------------------

    async def _on_capture(self, request: web.Request) -> web.Response:
        corr = request.headers.get(CORRELATION_HEADER)
        pending = self._pending.get(corr) if corr else None
        if corr is None or pending is None:
            return web.Response(status=400, text="missing/unknown correlation")

        pending.captured = CapturedRequest(
            path=request.path_qs,
            headers={k.lower(): v for k, v in request.headers.items()},
            body=await request.read(),
        )
        pending.captured_event.set()

        # Park: hold the connection open until the ext_proc response phase
        # supplies the provider's native response. From Portkey's side this
        # looks like a provider that is taking its time to answer. The
        # ``finally`` pop is the single cleanup point for every exit,
        # including cancellation (server shutdown mid-park, or deployments
        # that enable aiohttp handler cancellation on client disconnect).
        try:
            try:
                await asyncio.wait_for(pending.response_event.wait(),
                                       self._park_timeout)
            except asyncio.TimeoutError:
                return web.Response(
                    status=504, text="timed out awaiting provider response")

            body = pending.response
            if body is None:
                return web.Response(status=502, text="no provider response")
            return web.Response(
                status=200, body=body, content_type="application/json")
        finally:
            self._pending.pop(corr, None)
