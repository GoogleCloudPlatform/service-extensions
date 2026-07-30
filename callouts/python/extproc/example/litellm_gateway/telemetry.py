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

"""OpenTelemetry instrumentation for the LiteLLM gateway callout.

If OTEL_EXPORTER_OTLP_ENDPOINT is unset the
helpers are inert (start returns None, end is a no-op). When set, one span is
emitted per request using OTLP export and GenAI semantic-convention attributes.
LiteLLM's own otel callback fires on litellm.completion(), which this callout
never calls, so we instrument directly with the OpenTelemetry SDK.

Request cost is estimated via LiteLLM's bundled model price map
(litellm.cost_per_token) and attached as gen_ai.cost.total_cost; the
attribute is omitted when the model is not present in the price map. The
caller's API key is never logged verbatim: only a truncated SHA-256 hash
(user_api_key_hash) is attached, and it is omitted entirely when
gateway_config's redact_user_api_key_info setting is enabled or no key was
supplied. init_tracer() registers an atexit hook so buffered spans are
flushed (provider.shutdown()) on process exit.
"""

import atexit
import hashlib
import logging
import os
from typing import Any, Optional

import litellm
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from extproc.example.litellm_gateway import gateway_config

_tracer: Optional[trace.Tracer] = None
_enabled: bool = False


def init_tracer() -> None:
    """Initialize the global tracer once. No-op without an OTLP endpoint."""
    global _tracer, _enabled
    if _enabled:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        return
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    service_name = os.getenv("OTEL_SERVICE_NAME", "litellm-gateway")
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _install_provider(provider)
    atexit.register(provider.shutdown)
    logging.info(
        "OpenTelemetry enabled (%s) exporting to %s", protocol, endpoint)


def _install_provider(provider: TracerProvider) -> None:
    """Install a provider and mark tracing enabled. Also a test hook."""
    global _tracer, _enabled
    trace.set_tracer_provider(provider)
    _tracer = provider.get_tracer("litellm-gateway")
    _enabled = True


def _reset() -> None:
    """Test hook: disable tracing and drop the tracer."""
    global _tracer, _enabled
    _tracer = None
    _enabled = False


def enabled() -> bool:
    return _enabled


def start_request_span(headers: dict[str, str]) -> Optional[Any]:
    """Start a request span, parented to an inbound traceparent if present."""
    if not _enabled or _tracer is None:
        return None
    ctx = extract(headers)
    return _tracer.start_span("llm.request", context=ctx)


def _completion_cost(
    provider: str,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> Optional[float]:
    """USD cost via LiteLLM's bundled price map; None when unresolvable."""
    if prompt_tokens is None or completion_tokens is None:
        return None
    for candidate in (f"{provider}/{model}" if provider else model, model):
        try:
            input_cost, output_cost = litellm.cost_per_token(
                model=candidate,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens)
            return input_cost + output_cost
        except Exception:
            continue
    return None


def end_request_span(
    span: Optional[Any],
    *,
    provider: str,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_tokens: Optional[int],
    status: int,
    streaming: bool,
    operation: str = "chat",
    api_key: str = "",
    call_id: str = "",
) -> None:
    """Set GenAI attributes and end the span. No-op on a None span."""
    if span is None:
        return
    span.set_attribute("gen_ai.operation.name", operation)
    span.set_attribute("gen_ai.system", provider or "")
    span.set_attribute("gen_ai.request.model", model or "")
    if prompt_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
    if completion_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
    if total_tokens is not None:
        span.set_attribute("gen_ai.usage.total_tokens", total_tokens)
    cost = _completion_cost(
        provider, model, prompt_tokens, completion_tokens)
    if cost is not None:
        span.set_attribute("gen_ai.cost.total_cost", cost)
    if call_id:
        span.set_attribute("litellm.call_id", call_id)
    redact = gateway_config.telemetry_settings().redact_user_api_key_info
    if api_key and not redact:
        span.set_attribute(
            "user_api_key_hash",
            hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16])
    span.set_attribute("http.response.status_code", status)
    span.set_attribute("llm.is_streaming", streaming)
    span.end()
