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

"""Unit tests for the Portkey Gateway Python callout.

Pure unit tests: no gRPC server started, no Portkey sidecar started, no
network calls. Phase methods and helpers are called directly with synthetic
proto objects or simple inputs; HTTP interactions with the Portkey sidecar
are mocked via ``respx``.
"""

import asyncio
import gzip
import json
import os
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
from aiohttp import ClientSession

from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import (
    ProcessingMode,
)
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.example.portkey_gateway import service_callout_example as sce
from extproc.example.portkey_gateway.capture_server import (
    CORRELATION_HEADER,
    CaptureServer,
)
from extproc.example.portkey_gateway.portkey_client import PortkeyClient
from extproc.example.portkey_gateway.service_callout_example import (
    HEADER_PORTKEY_ROUTED,
    HEADER_PORTKEY_PROVIDER,
    PortkeyGatewayCallout,
    PROVIDERS,
    detect_provider_from_model,
    get_api_key,
    _state,
)

pytest_plugins = ["pytest_asyncio"]


def test_detect_provider_from_model_splits_first_segment():
    assert detect_provider_from_model(
        "anthropic/claude-3-5-sonnet-20241022") == (
        "anthropic", "claude-3-5-sonnet-20241022")
    assert detect_provider_from_model("groq/compound-beta") == (
        "groq", "compound-beta")
    assert detect_provider_from_model("openrouter/openai/gpt-oss-20b:free") == (
        "openrouter", "openai/gpt-oss-20b:free")


def test_detect_provider_defaults_to_vertex_ai_when_no_prefix():
    assert detect_provider_from_model("gemini-2.5-flash") == (
        "vertex_ai", "gemini-2.5-flash")


def test_providers_registry_has_four_supported_providers():
    assert set(PROVIDERS) == {"anthropic", "vertex_ai", "groq", "openrouter"}


def test_get_api_key_reads_env_var():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-xxx"}):
        assert get_api_key("anthropic") == "sk-ant-xxx"


def test_get_api_key_returns_none_for_vertex():
    assert get_api_key("vertex_ai") is None


def test_get_api_key_returns_none_for_unknown_provider():
    assert get_api_key("does-not-exist") is None


def test_mint_adc_token_returns_credentials_token():
    fake_creds = MagicMock()
    fake_creds.token = "ya29.fake-adc-token"
    fake_creds.valid = True
    with patch.object(sce, "_load_default_credentials",
                      return_value=fake_creds):
        assert sce.mint_adc_token() == "ya29.fake-adc-token"


def test_mint_adc_token_refreshes_when_invalid():
    fake_creds = MagicMock()
    fake_creds.valid = False
    fake_creds.token = "ya29.refreshed"

    def _refresh(_req):
        fake_creds.valid = True

    fake_creds.refresh.side_effect = _refresh
    with patch.object(sce, "_load_default_credentials",
                      return_value=fake_creds):
        assert sce.mint_adc_token() == "ya29.refreshed"
        assert fake_creds.refresh.called


@pytest.mark.asyncio
async def test_capture_parks_connection_until_response_is_provided():
    """The core of the loopback: Portkey's request is captured immediately,
    but its connection stays open until the provider's real response is
    supplied, so Portkey sees one request/response exchange."""
    server = CaptureServer(port=0)
    await server.start()
    provider_response = (
        b'{"id":"msg_real","content":[{"type":"text","text":"hello"}]}')
    try:
        await server.arm("corr-1")

        async with ClientSession() as s:
            post = asyncio.create_task(s.post(
                f"http://127.0.0.1:{server.port}/v1/messages",
                data=b'{"model":"claude-3","messages":[]}',
                headers={
                    "x-api-key": "sk-ant-xxx",
                    "anthropic-version": "2023-06-01",
                    CORRELATION_HEADER: "corr-1",
                },
            ))

            # The translated request is readable as soon as it is captured.
            captured = await server.wait_for_capture("corr-1", timeout=5)
            assert captured.body == b'{"model":"claude-3","messages":[]}'
            assert captured.path == "/v1/messages"
            assert captured.headers["x-api-key"] == "sk-ant-xxx"

            # The connection is parked: no response has been written yet.
            assert not post.done()

            # Unparking returns the provider's real bytes (no stub involved).
            await server.provide_response("corr-1", provider_response)
            r = await asyncio.wait_for(post, timeout=5)
            assert r.status == 200
            assert await r.read() == provider_response

        assert server._pending == {}
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_disarm_releases_parked_connection():
    """Abandoning a stream must not leave the connection parked until the
    park timeout expires."""
    server = CaptureServer(port=0)
    await server.start()
    try:
        await server.arm("corr-2")
        async with ClientSession() as s:
            post = asyncio.create_task(s.post(
                f"http://127.0.0.1:{server.port}/v1/messages",
                data=b"{}",
                headers={CORRELATION_HEADER: "corr-2"},
            ))
            await server.wait_for_capture("corr-2", timeout=5)
            await server.disarm("corr-2")
            r = await asyncio.wait_for(post, timeout=5)
            assert r.status == 502

        assert server._pending == {}
        # Disarming an unknown correlation is a no-op, not an error.
        await server.disarm("corr-never-armed")
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_park_timeout_returns_504_and_cleans_up():
    """A stream abandoned after the request phase (no provider response
    ever supplied) must not hold the parked connection forever."""
    server = CaptureServer(port=0, park_timeout=0.3)
    await server.start()
    try:
        await server.arm("corr-to")
        async with ClientSession() as s:
            r = await s.post(
                f"http://127.0.0.1:{server.port}/v1/messages",
                data=b"{}",
                headers={CORRELATION_HEADER: "corr-to"},
            )
            assert r.status == 504
        assert "corr-to" not in server._pending
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_capture_rejects_missing_correlation_header():
    server = CaptureServer(port=0)
    await server.start()
    try:
        async with ClientSession() as s:
            r = await s.post(
                f"http://127.0.0.1:{server.port}/anything",
                data=b"",
            )
            assert r.status == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
@respx.mock
async def test_translate_calls_portkey_with_expected_headers():
    route = respx.post("http://127.0.0.1:8787/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"id": "stub", "object": "chat.completion"}))
    client = PortkeyClient(base_url="http://127.0.0.1:8787")
    try:
        await client.translate(
            openai_body={"model": "claude-3-5-sonnet", "messages": []},
            provider="anthropic",
            api_key="sk-ant-xxx",
            custom_host="http://127.0.0.1:9999",
            correlation="corr-3",
            extra_headers={},
        )
    finally:
        await client.close()

    assert route.called
    req = route.calls.last.request
    assert req.headers["x-portkey-provider"] == "anthropic"
    assert req.headers["x-portkey-custom-host"] == "http://127.0.0.1:9999"
    assert req.headers["authorization"] == "Bearer sk-ant-xxx"
    assert req.headers["x-portkey-callout-correlation"] == "corr-3"
    # Correlation must be in the forwarded-headers list so Portkey passes
    # it on.
    forward = req.headers["x-portkey-forward-headers"]
    assert "x-portkey-callout-correlation" in forward
    # stream=true would be added by client if requested; force-false otherwise.
    body = json.loads(req.content)
    assert body["stream"] is False


@pytest.mark.asyncio
@respx.mock
async def test_translate_includes_extra_headers_in_forward_list():
    respx.post("http://127.0.0.1:8787/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={}))
    client = PortkeyClient(base_url="http://127.0.0.1:8787")
    try:
        await client.translate(
            openai_body={"model": "x", "messages": []},
            provider="vertex-ai",
            api_key="ya29.fake",
            custom_host="http://127.0.0.1:9999",
            correlation="corr-vx",
            extra_headers={
                "x-portkey-vertex-project-id": "test-project",
                "x-portkey-vertex-region": "us-central1",
            },
        )
    finally:
        await client.close()

    req = respx.calls.last.request
    forward_list = req.headers["x-portkey-forward-headers"]
    assert "x-portkey-callout-correlation" in forward_list
    assert "x-portkey-vertex-project-id" in forward_list
    assert "x-portkey-vertex-region" in forward_list
    # Vertex headers themselves are also set on the outbound request.
    assert req.headers["x-portkey-vertex-project-id"] == "test-project"
    assert req.headers["x-portkey-vertex-region"] == "us-central1"


@pytest.fixture(scope="module")
def svc():
    """Callout instance with no server started and no real GCP credentials."""
    with patch.dict(os.environ, {
        "GCP_PROJECT_ID": "test-project",
        "GCP_REGION": "us-central1",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "GROQ_API_KEY": "gsk-test",
        "OPENROUTER_API_KEY": "or-test",
        # Point at a port nothing is listening on; respx mocks the actual call.
        "PORTKEY_BASE_URL": "http://127.0.0.1:1",
        # Use an OS-picked ephemeral port so test runs never collide with
        # each other or with a real capture server.
        "CAPTURE_PORT": "0",
    }):
        callout = PortkeyGatewayCallout(
            disable_tls=True,
            combined_health_check=True,
            plaintext_address=("0.0.0.0", 0),
        )
        try:
            yield callout
        finally:
            if callout._callout_server is not None:
                callout._callout_server.stop()


def _release(svc, ctx) -> None:
    """Release the Portkey call a request-phase test leaves parked.

    In the real flow the response phase unparks the connection. Tests that
    stop after the request phase must do it explicitly, or the capture
    server holds the connection until its park timeout.
    """
    state = _state(ctx)
    if state.portkey_call is None:
        return
    svc._run_async(svc._capture.disarm(state.correlation))
    try:
        state.portkey_call.result(timeout=5)
    except Exception:
        pass
    state.portkey_call = None


def _http_headers(d: dict) -> service_pb2.HttpHeaders:
    hm = HeaderMap()
    for k, v in d.items():
        hm.headers.append(HeaderValue(key=k, raw_value=v.encode()))
    return service_pb2.HttpHeaders(headers=hm)


class _Ctx:
    """Minimal ServicerContext substitute: supports attribute assignment."""


def test_non_llm_path_is_passthrough(svc):
    ctx = _Ctx()
    resp = svc.on_request_headers(
        _http_headers({":path": "/", ":method": "GET"}), ctx)
    assert resp is None
    state = _state(ctx)
    assert state.is_llm is False


def test_llm_path_marks_state_and_stamps_routed_header(svc):
    ctx = _Ctx()
    resp = svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions", ":method": "POST"}),
        ctx,
    )
    assert resp is not None
    state = _state(ctx)
    assert state.is_llm is True
    assert state.correlation != ""  # uuid4 hex, ~32 chars
    headers = {
        hvo.header.key: hvo.header.raw_value.decode()
        for hvo in resp.request_headers.response.header_mutation.set_headers
    }
    assert headers[HEADER_PORTKEY_ROUTED] == "true"
    # BUFFERED body delivery is required: providers that flush response
    # bodies in several chunks (e.g. OpenRouter) break translation otherwise.
    assert resp.mode_override.request_body_mode == ProcessingMode.BUFFERED
    assert resp.mode_override.response_body_mode == ProcessingMode.BUFFERED
    # Browser-identifying headers must be stripped: Anthropic 401s requests
    # that carry an Origin header (direct-browser-access guard).
    removed = list(
        resp.request_headers.response.header_mutation.remove_headers)
    for h in ("origin", "referer", "cookie", "sec-fetch-mode"):
        assert h in removed


def test_response_headers_drops_content_length(svc):
    ctx = _Ctx()
    # Pretend we already saw a request-headers event for an LLM path.
    state = _state(ctx)
    state.is_llm = True
    resp = svc.on_response_headers(
        _http_headers({"content-length": "1234"}), ctx)
    removed = list(resp.response.header_mutation.remove_headers)
    assert "content-length" in removed
    # Stale gzip header must not survive the body transform.
    assert "content-encoding" in removed


@pytest.mark.asyncio
async def test_on_request_body_anthropic_drives_capture_and_rewrites(svc):
    """End-to-end: callout drives Portkey (mocked), capture records, callout
    returns provider-native bytes + headers."""
    async def fake_portkey(request: httpx.Request) -> httpx.Response:
        corr = request.headers["x-portkey-callout-correlation"]
        # Simulate Portkey: POST a translated Anthropic-format request to the
        # callout's capture server using the same correlation id.
        # Use an explicit real transport (bypassing respx) so the request
        # actually reaches the capture server running on the worker event loop.
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport()) as c:
            # Real Portkey strips the provider's URL prefix when forwarding to
            # custom_host (Anthropic's `/v1/messages` becomes `/messages`).
            # The callout's `api_path_prefix` reattaches `/v1` before the LB
            # forwards to api.anthropic.com.
            await c.post(
                f"http://127.0.0.1:{svc._capture.port}/messages",
                content=(b'{"model":"claude-3-5-sonnet","max_tokens":32,'
                         b'"messages":[{"role":"user","content":"hi"}]}'),
                headers={
                    "x-api-key": "sk-ant-test",
                    "anthropic-version": "2023-06-01",
                    "x-portkey-callout-correlation": corr,
                },
            )
        return httpx.Response(
            200, json={"id": "stub", "object": "chat.completion"})

    # Use the context-manager form so the route is registered on the local
    # router that is actually started and visible to the worker-thread httpx
    # calls.  The capture-server POST is registered as pass-through so
    # fake_portkey's real HTTP request actually reaches the aiohttp server
    # (rather than being auto-mocked to an empty 200 by respx).
    with respx.mock(
        assert_all_called=False, assert_all_mocked=False,
    ) as mock_router:
        mock_router.post("http://127.0.0.1:1/v1/chat/completions").mock(
            side_effect=fake_portkey)
        mock_router.route(
            host="127.0.0.1", port=svc._capture.port).pass_through()

        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({":path": "/v1/chat/completions"}), ctx)
        body = service_pb2.HttpBody(body=json.dumps({
            "model": "anthropic/claude-3-5-sonnet",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hi"}],
        }).encode())
        resp = svc.on_request_body(body, ctx)
        _release(svc, ctx)

    assert isinstance(resp, service_pb2.BodyResponse)
    new_body = resp.response.body_mutation.body
    parsed = json.loads(new_body)
    assert parsed["model"] == "claude-3-5-sonnet"
    assert parsed["messages"][0]["content"] == "hi"

    set_headers = {
        hvo.header.key: hvo.header.raw_value.decode()
        for hvo in resp.response.header_mutation.set_headers
    }
    assert set_headers[":authority"] == "api.anthropic.com"
    assert set_headers[":path"] == "/v1/messages"
    assert set_headers["x-api-key"] == "sk-ant-test"
    assert set_headers["anthropic-version"] == "2023-06-01"
    assert set_headers[HEADER_PORTKEY_PROVIDER] == "anthropic"
    # Internal correlation header must NOT leak to the provider.
    assert "x-portkey-callout-correlation" not in set_headers


def test_on_request_body_empty_body_is_passthrough(svc):
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    resp = svc.on_request_body(service_pb2.HttpBody(body=b""), ctx)
    # Unexpected but tolerated: logged as a warning and passed through.
    assert isinstance(resp, service_pb2.BodyResponse)
    assert resp.response.body_mutation.body == b""


def test_on_request_body_portkey_failure_disarms_capture(svc, monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("sidecar down")

    monkeypatch.setattr(svc._client, "translate", boom)
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    body = service_pb2.HttpBody(body=json.dumps({
        "model": "anthropic/claude-3-5-sonnet",
        "messages": [{"role": "user", "content": "hi"}],
    }).encode())
    resp = svc.on_request_body(body, ctx)
    assert resp.status.code == StatusCode.BadGateway
    # The failed correlation must not linger in the capture server.
    corr = _state(ctx).correlation
    assert corr not in svc._capture._pending


def test_on_request_body_anthropic_defaults_max_tokens(svc, monkeypatch):
    """Anthropic's Messages API requires max_tokens; OpenAI clients usually
    omit it. The callout must fill in the spec default, but never override
    a client-provided value."""
    captured = {}

    async def fake_translate(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(svc._client, "translate", fake_translate)

    # Client omits max_tokens: the spec default is injected.
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    body = service_pb2.HttpBody(body=json.dumps({
        "model": "anthropic/claude-haiku-4-5",
        "messages": [{"role": "user", "content": "hi"}],
    }).encode())
    svc.on_request_body(body, ctx)
    assert captured["openai_body"]["max_tokens"] == 4096

    # Client sets max_tokens: passed through untouched.
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    body = service_pb2.HttpBody(body=json.dumps({
        "model": "anthropic/claude-haiku-4-5",
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode())
    svc.on_request_body(body, ctx)
    assert captured["openai_body"]["max_tokens"] == 32


def test_on_request_body_fast_fails_when_portkey_never_posts(
        svc, monkeypatch):
    """If Portkey answers with its own error response instead of POSTing to
    the capture server, the callout must fail promptly rather than sitting
    out the full capture timeout."""
    async def error_without_post(**kwargs):
        return httpx.Response(424, text="unsupported provider config")

    monkeypatch.setattr(svc._client, "translate", error_without_post)
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    body = service_pb2.HttpBody(body=json.dumps({
        "model": "anthropic/claude-haiku-4-5",
        "messages": [{"role": "user", "content": "hi"}],
    }).encode())
    start = time.monotonic()
    resp = svc.on_request_body(body, ctx)
    elapsed = time.monotonic() - start
    assert resp.status.code == StatusCode.BadGateway
    # The fast path, not the 30s capture timeout.
    assert elapsed < 10
    assert _state(ctx).correlation not in svc._capture._pending


def test_on_request_body_invalid_json_returns_400(svc):
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    resp = svc.on_request_body(service_pb2.HttpBody(body=b"not json"), ctx)
    # on_request_body returns ImmediateResponse directly; the gRPC server wraps
    # it in ProcessingResponse(immediate_response=...) at dispatch time.
    assert resp.status.code == StatusCode.BadRequest


def test_on_request_body_missing_model_returns_400(svc):
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    body = service_pb2.HttpBody(body=json.dumps({"messages": []}).encode())
    resp = svc.on_request_body(body, ctx)
    assert resp.status.code == StatusCode.BadRequest


def test_on_request_body_unknown_provider_returns_400(svc):
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    body = service_pb2.HttpBody(body=json.dumps({
        "model": "mistral/mistral-large", "messages": [],
    }).encode())
    resp = svc.on_request_body(body, ctx)
    assert resp.status.code == StatusCode.BadRequest


@pytest.mark.asyncio
async def test_full_cycle_translates_anthropic_response_to_openai(svc):
    """One Portkey call spans both phases: the callout reads the translated
    request off the parked connection, later writes the provider's response
    onto that same connection, and the call resolves with OpenAI format."""
    with respx.mock(
        base_url="http://127.0.0.1:1",
        assert_all_mocked=False,
        assert_all_called=False,
    ) as mock_router:
        # Let the inner httpx.AsyncClient hit the real localhost capture server.
        mock_router.route(
            host="127.0.0.1", port=svc._capture.port
        ).pass_through()

        capture_port = svc._capture.port

        async def fake_portkey(request: httpx.Request) -> httpx.Response:
            corr = request.headers[CORRELATION_HEADER]
            # Portkey POSTs the translated request, then blocks on the parked
            # connection until the callout supplies the provider's response.
            async with httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport()) as c:
                r = await c.post(
                    f"http://127.0.0.1:{capture_port}/messages",
                    content=(b'{"model":"claude-3-5-sonnet","max_tokens":32,'
                             b'"messages":[{"role":"user","content":"hi"}]}'),
                    headers={
                        "x-api-key": "sk-ant-test",
                        CORRELATION_HEADER: corr,
                    },
                    timeout=30,
                )
                provider_body = await r.aread()
            # Portkey now translates the provider response it just received.
            assert b'"msg_real"' in provider_body
            return httpx.Response(200, json={
                "id": "chatcmpl-fake",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "hi back"},
                    "finish_reason": "stop",
                }],
            })

        mock_router.post("/v1/chat/completions").mock(side_effect=fake_portkey)

        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({":path": "/v1/chat/completions"}), ctx)
        req = json.dumps({
            "model": "anthropic/claude-3-5-sonnet",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        req_resp = svc.on_request_body(service_pb2.HttpBody(body=req), ctx)
        assert isinstance(req_resp, service_pb2.BodyResponse)

        anthropic_response = (
            b'{"id":"msg_real","type":"message",'
            b'"content":[{"type":"text","text":"hi back"}],'
            b'"usage":{"input_tokens":1,"output_tokens":2}}'
        )
        body = service_pb2.HttpBody(body=anthropic_response, end_of_stream=True)
        resp = svc.on_response_body(body, ctx)

        assert isinstance(resp, service_pb2.BodyResponse)
        new_body = json.loads(resp.response.body_mutation.body)
        assert new_body["object"] == "chat.completion"
        assert new_body["choices"][0]["message"]["content"] == "hi back"
        # The parked connection is resolved and its state cleaned up.
        assert _state(ctx).correlation not in svc._capture._pending


@pytest.mark.asyncio
async def test_on_response_body_reassembles_chunked_gzip_response(svc):
    """Replicates the production OpenRouter behavior: a gzipped provider
    response delivered as several STREAMED chunks. The callout must buffer
    the chunks, gunzip the reassembled body, and translate it."""
    with respx.mock(
        base_url="http://127.0.0.1:1",
        assert_all_mocked=False,
        assert_all_called=False,
    ) as mock_router:
        mock_router.route(
            host="127.0.0.1", port=svc._capture.port
        ).pass_through()

        capture_port = svc._capture.port

        async def fake_portkey(request: httpx.Request) -> httpx.Response:
            corr = request.headers[CORRELATION_HEADER]
            async with httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport()) as c:
                r = await c.post(
                    f"http://127.0.0.1:{capture_port}/v1/chat/completions",
                    content=(b'{"model":"openai/gpt-oss-20b:free",'
                             b'"messages":[{"role":"user","content":"hi"}]}'),
                    headers={CORRELATION_HEADER: corr},
                    timeout=30,
                )
                provider_body = await r.aread()
            # The unparked body must be the gunzipped, reassembled JSON.
            unparked = json.loads(provider_body)
            assert unparked["id"] == "gen-or-1"
            return httpx.Response(200, json={
                "id": "chatcmpl-or",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "hi back"},
                    "finish_reason": "stop",
                }],
            })

        mock_router.post("/v1/chat/completions").mock(side_effect=fake_portkey)

        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({":path": "/v1/chat/completions"}), ctx)
        req = json.dumps({
            "model": "openrouter/openai/gpt-oss-20b:free",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        assert isinstance(
            svc.on_request_body(service_pb2.HttpBody(body=req), ctx),
            service_pb2.BodyResponse)

        compressed = gzip.compress(
            b'{"id":"gen-or-1","object":"chat.completion","choices":[]}')
        # Split mid-stream so neither later fragment carries the gzip magic.
        first, second, last = (
            compressed[:5], compressed[5:11], compressed[11:])
        for fragment in (first, second):
            r = svc.on_response_body(
                service_pb2.HttpBody(body=fragment, end_of_stream=False), ctx)
            assert r.response.body_mutation.clear_body is True
        resp = svc.on_response_body(
            service_pb2.HttpBody(body=last, end_of_stream=True), ctx)

        assert isinstance(resp, service_pb2.BodyResponse)
        new_body = json.loads(resp.response.body_mutation.body)
        assert new_body["id"] == "chatcmpl-or"
        assert new_body["choices"][0]["message"]["content"] == "hi back"


def test_on_response_body_returns_none_for_non_llm(svc):
    ctx = _Ctx()
    # Don't set state.is_llm; default state.is_llm is False.
    body = service_pb2.HttpBody(body=b"anything", end_of_stream=True)
    assert svc.on_response_body(body, ctx) is None


def test_on_response_body_buffers_mid_stream_chunks(svc):
    ctx = _Ctx()
    state = _state(ctx)
    state.is_llm = True
    # A mid-stream chunk (end_of_stream=False) is buffered in state and
    # cleared from the egress; translation waits for the final chunk.
    body = service_pb2.HttpBody(body=b"partial", end_of_stream=False)
    resp = svc.on_response_body(body, ctx)
    assert isinstance(resp, service_pb2.BodyResponse)
    assert resp.response.body_mutation.clear_body is True
    assert state.response_chunks == [b"partial"]


def test_on_response_body_missing_provider_returns_500(svc):
    ctx = _Ctx()
    state = _state(ctx)
    state.is_llm = True
    # state.provider stays None (never set by a normal flow).
    body = service_pb2.HttpBody(body=b"{}", end_of_stream=True)
    resp = svc.on_response_body(body, ctx)
    assert resp.status.code == StatusCode.InternalServerError


def test_on_request_body_rejects_streaming_for_now(svc):
    ctx = _Ctx()
    svc.on_request_headers(
        _http_headers({":path": "/v1/chat/completions"}), ctx)
    body = service_pb2.HttpBody(body=json.dumps({
        "model": "anthropic/claude-3-5-sonnet",
        "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode())
    resp = svc.on_request_body(body, ctx)
    assert resp.status.code == StatusCode.NotImplemented


@pytest.mark.asyncio
async def test_on_request_body_vertex_uses_adc_token_and_region(svc):
    with respx.mock(
        base_url="http://127.0.0.1:1",
        assert_all_mocked=False,
        assert_all_called=False,
    ) as mock_router:
        mock_router.route(
            host="127.0.0.1", port=svc._capture.port
        ).pass_through()

        capture_port = svc._capture.port
        # Vertex AI is the no-prefix provider: Portkey emits the full
        # generateContent path, so the callout forwards it verbatim.
        vertex_path = (
            "/v1/projects/test-project/locations/us-central1"
            "/publishers/google/models/gemini-2.5-flash:generateContent"
        )
        vertex_body = b'{"contents":[{"role":"user","parts":[{"text":"hi"}]}]}'

        async def fake_portkey(request: httpx.Request) -> httpx.Response:
            corr = request.headers["x-portkey-callout-correlation"]
            # Verify Portkey received the Vertex project/region headers + ADC.
            assert request.headers[
                "x-portkey-vertex-project-id"] == "test-project"
            assert request.headers["x-portkey-vertex-region"] == "us-central1"
            assert request.headers["authorization"] == "Bearer ya29.fake"
            async with httpx.AsyncClient() as c:
                # Simulate Portkey POSTing a Vertex generateContent request to
                # the capture server.
                await c.post(
                    f"http://127.0.0.1:{capture_port}{vertex_path}",
                    content=vertex_body,
                    headers={
                        "authorization": "Bearer ya29.fake",
                        "x-portkey-callout-correlation": corr,
                    },
                )
            return httpx.Response(200, json={})

        mock_router.post("/v1/chat/completions").mock(side_effect=fake_portkey)

        with patch(
            "extproc.example.portkey_gateway.service_callout_example"
            ".mint_adc_token",
            return_value="ya29.fake",
        ):
            ctx = _Ctx()
            svc.on_request_headers(
                _http_headers({":path": "/v1/chat/completions"}), ctx)
            req = json.dumps({
                "model": "vertex_ai/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}],
            }).encode()
            resp = svc.on_request_body(service_pb2.HttpBody(body=req), ctx)
            _release(svc, ctx)

        assert isinstance(resp, service_pb2.BodyResponse)
        set_headers = {
            hvo.header.key: hvo.header.raw_value.decode()
            for hvo in resp.response.header_mutation.set_headers
        }
        assert set_headers[":authority"] == (
            "us-central1-aiplatform.googleapis.com")
        # No api_path_prefix for Vertex: the captured path passes through.
        assert set_headers[":path"] == vertex_path
        assert set_headers["authorization"] == "Bearer ya29.fake"
        # Provenance stamp uses Portkey's id ("vertex-ai"), not the
        # client-facing "vertex_ai" prefix.
        assert set_headers[HEADER_PORTKEY_PROVIDER] == "vertex-ai"


@pytest.mark.asyncio
async def test_on_request_body_groq_uses_api_key_env(svc):
    with respx.mock(
        base_url="http://127.0.0.1:1",
        assert_all_mocked=False,
        assert_all_called=False,
    ) as mock_router:
        mock_router.route(
            host="127.0.0.1", port=svc._capture.port
        ).pass_through()

        capture_port = svc._capture.port

        async def fake_portkey(request: httpx.Request) -> httpx.Response:
            corr = request.headers["x-portkey-callout-correlation"]
            assert request.headers["authorization"] == "Bearer gsk-test"
            async with httpx.AsyncClient() as c:
                # Real Portkey strips Groq's "/openai/v1" URL prefix when
                # forwarding to custom_host; the callout reattaches it via
                # api_path_prefix.
                await c.post(
                    f"http://127.0.0.1:{capture_port}/chat/completions",
                    content=(b'{"model":"compound-beta","messages":'
                             b'[{"role":"user","content":"hi"}]}'),
                    headers={
                        "authorization": "Bearer gsk-test",
                        "x-portkey-callout-correlation": corr,
                    },
                )
            return httpx.Response(200, json={})

        mock_router.post("/v1/chat/completions").mock(side_effect=fake_portkey)

        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({":path": "/v1/chat/completions"}), ctx)
        req = json.dumps({
            "model": "groq/compound-beta",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        resp = svc.on_request_body(service_pb2.HttpBody(body=req), ctx)
        _release(svc, ctx)

        assert isinstance(resp, service_pb2.BodyResponse)
        set_headers = {
            hvo.header.key: hvo.header.raw_value.decode()
            for hvo in resp.response.header_mutation.set_headers
        }
        assert set_headers[":authority"] == "api.groq.com"
        assert set_headers[":path"] == "/openai/v1/chat/completions"
        assert set_headers["authorization"] == "Bearer gsk-test"
        assert set_headers[HEADER_PORTKEY_PROVIDER] == "groq"


@pytest.mark.asyncio
async def test_on_request_body_openrouter_preserves_inner_slash_in_model(svc):
    with respx.mock(
        base_url="http://127.0.0.1:1",
        assert_all_mocked=False,
        assert_all_called=False,
    ) as mock_router:
        mock_router.route(
            host="127.0.0.1", port=svc._capture.port
        ).pass_through()

        capture_port = svc._capture.port

        async def fake_portkey(request: httpx.Request) -> httpx.Response:
            corr = request.headers["x-portkey-callout-correlation"]
            assert request.headers["authorization"] == "Bearer or-test"
            # Body Portkey received should have the openrouter prefix stripped,
            # but the inner provider/model preserved.
            body = json.loads(request.content)
            assert body["model"] == "openai/gpt-oss-20b:free"
            async with httpx.AsyncClient() as c:
                # Real Portkey strips OpenRouter's "/api" URL prefix when
                # forwarding to custom_host; the callout reattaches it via
                # api_path_prefix.
                await c.post(
                    f"http://127.0.0.1:{capture_port}/v1/chat/completions",
                    content=(b'{"model":"openai/gpt-oss-20b:free","messages":'
                             b'[{"role":"user","content":"hi"}]}'),
                    headers={
                        "authorization": "Bearer or-test",
                        "x-portkey-callout-correlation": corr,
                    },
                )
            return httpx.Response(200, json={})

        mock_router.post("/v1/chat/completions").mock(side_effect=fake_portkey)

        ctx = _Ctx()
        svc.on_request_headers(
            _http_headers({":path": "/v1/chat/completions"}), ctx)
        req = json.dumps({
            "model": "openrouter/openai/gpt-oss-20b:free",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        resp = svc.on_request_body(service_pb2.HttpBody(body=req), ctx)
        _release(svc, ctx)

        assert isinstance(resp, service_pb2.BodyResponse)
        set_headers = {
            hvo.header.key: hvo.header.raw_value.decode()
            for hvo in resp.response.header_mutation.set_headers
        }
        assert set_headers[":authority"] == "openrouter.ai"
        assert set_headers[":path"] == "/api/v1/chat/completions"
        assert set_headers["authorization"] == "Bearer or-test"
        assert set_headers[HEADER_PORTKEY_PROVIDER] == "openrouter"
