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
(litellm.cost_per_token) and attached as litellm.cost.total_cost; the
attribute is omitted when the model is not present in the price map. The
caller's API key is never logged verbatim: only a truncated SHA-256 hash
(user_api_key_hash) is attached, and it is omitted entirely when
gateway_config's redact_user_api_key_info setting is enabled or no key was
supplied. Buffered spans are flushed on process exit by TracerProvider's own
atexit hook, which it installs by default (shutdown_on_exit).
"""

import hashlib
import logging
import os
from typing import Any, Optional

import litellm
from opentelemetry import metrics, trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import (
    ExplicitBucketHistogramAggregation,
    View,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as GrpcMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GrpcSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as HttpMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HttpSpanExporter,
)

from extproc.example.litellm_gateway import gateway_config

# Both ladders are copied verbatim from the OpenTelemetry GenAI semantic
# conventions, along with the units declared on the instruments below
# ({token} and s). Those metrics are Development stability, so the advice
# can still change; re-check the source before treating them as fixed.
# https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md
_TOKEN_BUCKETS = [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144,
                  1048576, 4194304, 16777216, 67108864]
_DURATION_BUCKETS = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56,
                     5.12, 10.24, 20.48, 40.96, 81.92]

_METRIC_VIEWS = (
    View(instrument_name="gen_ai.client.token.usage",
         aggregation=ExplicitBucketHistogramAggregation(_TOKEN_BUCKETS)),
    View(instrument_name="gen_ai.client.operation.duration",
         aggregation=ExplicitBucketHistogramAggregation(_DURATION_BUCKETS)),
)


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


class Telemetry:
    """Request tracing, inert unless an OTLP endpoint is configured.

    A Telemetry with no tracer is a working no-op rather than a special
    case, so callers never branch on whether tracing is on: start a span,
    get None, and ending None does nothing.
    """

    def __init__(
        self,
        tracer: Optional[trace.Tracer] = None,
        settings: Optional["gateway_config.TelemetrySettings"] = None,
        meter: Optional[metrics.Meter] = None,
    ) -> None:
        self._tracer = tracer
        self._redact = (
            settings.redact_user_api_key_info if settings else True)
        self._tokens = self._duration = None
        if meter is not None:
            self._tokens = meter.create_histogram(
                "gen_ai.client.token.usage", unit="{token}",
                description="Number of input and output tokens used.")
            self._duration = meter.create_histogram(
                "gen_ai.client.operation.duration", unit="s",
                description="GenAI operation duration.")

    @classmethod
    def from_env(
        cls,
        settings: Optional["gateway_config.TelemetrySettings"] = None,
    ) -> "Telemetry":
        """Build from OTEL_* env vars. Tracing stays off without an endpoint."""
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if not endpoint:
            return cls(settings=settings)
        protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
        service_name = os.getenv("OTEL_SERVICE_NAME", "litellm-gateway")
        grpc = protocol == "grpc"
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(
            (GrpcSpanExporter if grpc else HttpSpanExporter)()))
        trace.set_tracer_provider(provider)

        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(
                (GrpcMetricExporter if grpc else HttpMetricExporter)())],
            views=_METRIC_VIEWS)
        metrics.set_meter_provider(meter_provider)

        logging.info(
            "OpenTelemetry enabled (%s) exporting to %s", protocol, endpoint)
        return cls(
            tracer=provider.get_tracer("litellm-gateway"),
            meter=meter_provider.get_meter("litellm-gateway"),
            settings=settings)

    @classmethod
    def from_provider(
        cls,
        provider: TracerProvider,
        settings: Optional["gateway_config.TelemetrySettings"] = None,
        meter_provider: Optional[MeterProvider] = None,
    ) -> "Telemetry":
        """Build around already-configured providers. Used by tests."""
        return cls(
            tracer=provider.get_tracer("litellm-gateway"),
            meter=(meter_provider.get_meter("litellm-gateway")
                   if meter_provider else None),
            settings=settings)

    def enabled(self) -> bool:
        """True when a tracer is installed."""
        return self._tracer is not None

    def start_request_span(self, headers: dict[str, str]) -> Optional[Any]:
        """Start a span, parented to an inbound traceparent if present.

        The span opens before the body is read, so neither the operation nor
        the model is known yet. It is named on the request leg and renamed
        in end_request_span() once both are, which is what the GenAI
        semantic conventions ask for.
        """
        if self._tracer is None:
            return None
        return self._tracer.start_span(
            "llm.request", context=extract(headers))

    def end_request_span(
        self,
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
        requested_model: str = "",
        routing_strategy: str = "",
        duration_s: Optional[float] = None,
    ) -> None:
        """Set GenAI attributes, end the span, and record the metrics.

        The span and the metrics are emitted together so they cannot
        disagree, but a request whose span was suppressed
        (x-litellm-disable-callbacks: otel) still counts toward the
        metrics.
        """
        self._record_metrics(
            provider=provider, model=model, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, status=status,
            operation=operation, duration_s=duration_s)
        if span is None:
            return
        # GenAI semconv names a span "{operation} {model}". Both are only
        # known once the body has been read, so the name is set here.
        # Rejected requests (quota, bad body) end with no model; they get
        # the spec shape minus the model rather than keeping the
        # placeholder name the span was opened with.
        span.update_name(f"{operation} {model}" if model else operation)
        # The served model can differ from the one the client asked for,
        # because a routing strategy or header override rewrote it. The
        # caller passes requested_model only when that happened (comparing
        # full LiteLLM ids; comparing against the provider-stripped `model`
        # here would fire on every prefixed request). Both attributes sit
        # under `litellm.` rather than `gen_ai.`: the spec owns that
        # namespace and defines neither.
        if requested_model:
            span.set_attribute("litellm.request.original_model",
                               requested_model)
        if routing_strategy:
            span.set_attribute("litellm.routing_strategy", routing_strategy)
        span.set_attribute("gen_ai.operation.name", operation)
        span.set_attribute("gen_ai.provider.name", provider or "")
        span.set_attribute("gen_ai.request.model", model or "")
        if prompt_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
        if completion_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
        if total_tokens is not None:
            # input_tokens and output_tokens are the spec's; a total and a
            # cost are useful but the spec defines neither, so they live
            # under `litellm.`.
            span.set_attribute("litellm.usage.total_tokens", total_tokens)
        cost = _completion_cost(
            provider, model, prompt_tokens, completion_tokens)
        if cost is not None:
            span.set_attribute("litellm.cost.total_cost", cost)
        if call_id:
            span.set_attribute("litellm.call_id", call_id)
        if api_key and not self._redact:
            span.set_attribute(
                "user_api_key_hash",
                hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16])
        span.set_attribute("http.response.status_code", status)
        span.set_attribute("llm.is_streaming", streaming)
        span.end()

    def _record_metrics(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        status: int,
        operation: str,
        duration_s: Optional[float],
    ) -> None:
        """Emit the two GenAI client metrics. No-op without a meter."""
        if self._tokens is None or self._duration is None:
            return
        attrs = {
            "gen_ai.operation.name": operation,
            "gen_ai.provider.name": provider or "",
            "gen_ai.request.model": model or "",
        }
        # error.type is only set when the operation failed, per the spec.
        if status >= 400:
            attrs["error.type"] = str(status)
        for token_type, count in (("input", prompt_tokens),
                                  ("output", completion_tokens)):
            if count is not None:
                self._tokens.record(
                    count, {**attrs, "gen_ai.token.type": token_type})
        if duration_s is not None:
            self._duration.record(duration_s, attrs)
