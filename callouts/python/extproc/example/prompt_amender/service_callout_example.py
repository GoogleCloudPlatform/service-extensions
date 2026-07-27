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

"""Prompt-Amender callout: a pure ext_proc adapter.

Centralized governance proxy that dynamically inspects and mutates system
instructions sent to LLMs at the network layer. The callout evaluates each
request's caller identity, host, and path against a hot-reloadable YAML
ruleset; on a match it mutates the request's `systemInstruction.parts[].text`
field before forwarding to the LLM backend (e.g. Vertex AI).

Two-phase design, mirroring the Envoy processing model other examples in
this collection use:

  Header phase (`on_request_headers`): extract the caller's SPIFFE ID
  (from the trusted `x-spiffe-id` header the Agent Gateway injects after
  mTLS/SVID validation -- see the README for why this header must be
  stripped from the client-supplied request first), `:authority`, and
  `:path`; evaluate against the active ruleset. On a match, override
  `mode_override.request_body_mode` to `BUFFERED` so the gateway streams
  us the body; on no match, override it to `NONE` so we never pay
  body-buffering latency for traffic the ruleset doesn't care about. This
  mirrors the technique the litellm_gateway example uses on the *response*
  body mode; here it's applied to the *request* body. Whether the managed
  Traffic Extension actually honors a request-side mode_override has not
  been verified against a real deployment (see the README) -- if it turns
  out not to be, this still degrades safely: `on_request_body` already
  returns a pass-through response whenever no rule matched, regardless of
  why the body arrived.

  Body phase (`on_request_body`): parse the buffered JSON body, locate
  `systemInstruction.parts[].text` (accepting the legacy `system_instruction`
  spelling too, and inserting an empty one if the request has neither --
  see `_locate_system_instruction`), apply the matched rule's mutation
  (prepend/append/replace/template), and return the re-serialized body plus
  a recalculated Content-Length.

`prompt_amender` owns:
  * selector matching (identity/host/path glob) and mutation operations
    (rule_engine.py)
  * hot-reloadable rule sourcing from env/GCS/git with atomic swap and
    validation-reject (config_sources.py)

The callout owns:
  * Envoy ext_proc protobuf adapter (via `extproc.service.callout_server`)
  * per-request body-subscription decision via `mode_override`
  * structured JSON logging that never includes raw prompt text (only
    rule_id, op, caller_spiffe_id, original_len, new_len, latency_ms) and
    never includes raw template-error text on failure (only the exception
    type name, since a Jinja2 TemplateError's message can echo the
    offending template content)
"""

import json
import logging
import os
import time

from grpc import ServicerContext
from opentelemetry import trace
from opentelemetry.propagate import extract

from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import (
    ProcessingMode)
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.service import callout_server
from extproc.service import callout_tools

from extproc.example.prompt_amender import metrics
from extproc.example.prompt_amender.config_sources import (
    HotReloadingRuleProvider, build_config_source)
from extproc.example.prompt_amender.logging_utils import (
    configure_json_logging, log_fields)
from extproc.example.prompt_amender.rule_engine import (
    Rule, TemplateRenderError, apply_action)

SPIFFE_HEADER = "x-spiffe-id"
AUTHORITY_HEADER = ":authority"
PATH_HEADER = ":path"
TRACEPARENT_HEADER = "traceparent"

_LOGGER = logging.getLogger("prompt_amender")
_TRACER = trace.get_tracer("prompt_amender")


class BodyTooLargeError(Exception):
  pass


def _state(context: ServicerContext) -> dict:
  state = getattr(context, "_prompt_amender_state", None)
  if state is None:
    state = {}
    context._prompt_amender_state = state
  return state


def _locate_system_instruction(payload: dict) -> tuple[dict, list]:
  """Finds (or creates) the systemInstruction object and its parts list.

  Accepts both the canonical proto3 JSON spelling `systemInstruction`
  (what every official Vertex/Gemini SDK sends) and the legacy
  `system_instruction` spelling. If the request has neither -- the CUJ 3
  scenario, where an agent sends a raw request and expects the amender to
  inject governance from scratch -- a new `systemInstruction` object with
  one empty text part is created and attached to the payload, rather than
  raising. Previously, only `system_instruction` was recognized, so real
  Vertex traffic missed the lookup, the callout raised, and with
  FAIL_OPEN=true the request passed through with governance silently not
  applied for essentially all real traffic -- and any client could opt out
  of governance simply by omitting the field. Fail-open must cover
  malformed input, not policy bypass, so this function guarantees a
  system-instruction object exists rather than treating its absence as an
  error.
  """
  key = "systemInstruction" if "systemInstruction" in payload else "system_instruction"
  si = payload.get(key)
  if si is None:
    si = {"parts": [{"text": ""}]}
    payload["systemInstruction"] = si
    key = "systemInstruction"

  parts = si.get("parts")
  if not isinstance(parts, list):
    parts = []
    si["parts"] = parts

  text_part = next((p for p in parts if isinstance(p, dict) and "text" in p),
                    None)
  if text_part is None:
    text_part = {"text": ""}
    parts.append(text_part)

  return payload, parts


def _configure_otel_sdk() -> None:
  """Registers real OTEL SDK providers so the counters in metrics.py and
  the `prompt_amender.amend` span actually export somewhere, rather than
  quietly staying no-ops forever. Only runs when OTEL_EXPORTER_OTLP_ENDPOINT
  is set; otherwise the opentelemetry-api default no-op implementation
  stays in place, which is safe (calls succeed, nothing is exported) but
  means CUJ 2/4's metric- and trace-based verification steps have nothing
  to inspect. Requires opentelemetry-sdk and opentelemetry-exporter-otlp,
  both in additional-requirements.txt.
  """
  otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
  if not otlp_endpoint:
    return

  from opentelemetry import metrics as otel_metrics
  from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
      OTLPMetricExporter)
  from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
      OTLPSpanExporter)
  from opentelemetry.sdk.metrics import MeterProvider
  from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
  from opentelemetry.sdk.resources import Resource
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import BatchSpanProcessor

  resource = Resource.create({"service.name": "prompt-amender"})

  otel_metrics.set_meter_provider(MeterProvider(
      resource=resource,
      metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
  ))
  trace.set_tracer_provider(TracerProvider(resource=resource))
  trace.get_tracer_provider().add_span_processor(
      BatchSpanProcessor(OTLPSpanExporter()))


class PromptAmenderCallout(callout_server.CalloutServer):
  """Ext_proc callout that mutates LLM system instructions in-transit."""

  def __init__(self, **kwargs) -> None:
    super().__init__(**kwargs)
    configure_json_logging(os.getenv("LOG_LEVEL", "INFO"))
    _configure_otel_sdk()

    self.fail_open = os.getenv("FAIL_OPEN", "true").lower() == "true"
    self.max_request_body_bytes = int(
        os.getenv("MAX_REQUEST_BODY_BYTES", str(4 * 1024 * 1024)))

    source = build_config_source(
        source=os.getenv("CONFIG_SOURCE", "gcs"),
        config_value=os.getenv("CONFIG_VALUE", ""),
        gcs_rules_uri=os.getenv("GCS_RULES_URI", ""),
        git_repo_url=os.getenv("GIT_REPO_URL", ""),
        git_branch=os.getenv("GIT_BRANCH", "main"),
        git_rules_path=os.getenv("GIT_RULES_PATH", "rules.yaml"),
    )
    self.rule_provider = HotReloadingRuleProvider(
        source=source,
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "15")),
    )
    # Deliberately unguarded: at startup there is no last-known-good
    # ruleset, so a fetch/parse failure here must crash-loop the container
    # visibly rather than boot a healthy-looking service enforcing zero
    # rules. See config_sources.HotReloadingRuleProvider.load_initial.
    self.rule_provider.load_initial()
    self.rule_provider.start_background_polling()
    log_fields(_LOGGER, logging.INFO, "prompt-amender rules loaded",
               rule_count=len(self.rule_provider.current().rules))

  # ---------------------------------------------------------------- phases

  def on_request_headers(
      self,
      headers: service_pb2.HttpHeaders,
      context: ServicerContext,
  ) -> service_pb2.ProcessingResponse | None:
    spiffe_id, host, path, traceparent = "", "", "", ""
    for h in headers.headers.headers:
      key = h.key.lower()
      value = (h.raw_value or h.value.encode("utf-8")).decode(
          "utf-8", errors="replace")
      if key == SPIFFE_HEADER:
        spiffe_id = value
      elif key in (AUTHORITY_HEADER, "host"):
        host = value
      elif key == PATH_HEADER:
        path = value
      elif key == TRACEPARENT_HEADER:
        traceparent = value

    ruleset = self.rule_provider.current()
    matched_rule = ruleset.find_match(spiffe_id, host, path)

    state = _state(context)
    state["matched_rule"] = matched_rule
    state["spiffe_id"] = spiffe_id
    state["host"] = host
    state["path"] = path
    state["traceparent"] = traceparent

    resp = service_pb2.ProcessingResponse()
    mode = ProcessingMode()
    if matched_rule is None:
      metrics.requests_total.add(1, {"outcome": "skip"})
      # No rule cares about this request -- skip body buffering entirely
      # so unmatched traffic pays near-zero latency tax. NOTE: whether the
      # managed Traffic Extension honors mode_override on the request path
      # is unverified (see README); on_request_body already no-ops when no
      # rule matched, so this degrades safely either way.
      mode.request_body_mode = ProcessingMode.NONE
    else:
      mode.request_body_mode = ProcessingMode.BUFFERED
    resp.mode_override.CopyFrom(mode)
    return resp

  def on_request_body(
      self,
      body: service_pb2.HttpBody,
      context: ServicerContext,
  ) -> service_pb2.BodyResponse | None:
    state = _state(context)
    matched_rule: Rule | None = state.get("matched_rule")
    if matched_rule is None:
      # Shouldn't happen when mode_override is honored, but pass through
      # safely if the body arrives anyway.
      metrics.requests_total.add(1, {"outcome": "skip"})
      return None

    ctx = extract({"traceparent": state.get("traceparent", "")})
    with _TRACER.start_as_current_span("prompt_amender.amend", context=ctx):
      start = time.monotonic()
      try:
        mutated_body, original_len, new_len = self._mutate(
            body.body, matched_rule, state)
      except (BodyTooLargeError, TemplateRenderError, ValueError) as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        # Log only the exception TYPE, never str(exc): a Jinja2
        # TemplateRenderError's message can echo the offending template
        # text, and this path must never leak prompt/template content into
        # logs.
        log_fields(
            _LOGGER, logging.ERROR,
            "prompt amendment failed; passing request through unmodified",
            rule_id=matched_rule.id, op=matched_rule.action.operation.value,
            caller_spiffe_id=state.get("spiffe_id", ""),
            error_type=type(exc).__name__, latency_ms=round(elapsed_ms, 2))
        metrics.requests_total.add(1, {"outcome": "error"})
        metrics.amend_latency_seconds.record(elapsed_ms / 1000)
        if self.fail_open:
          return None
        return callout_tools.header_immediate_response(
            StatusCode.InternalServerError)

      elapsed_ms = (time.monotonic() - start) * 1000
      log_fields(
          _LOGGER, logging.INFO, "prompt amendment applied",
          rule_id=matched_rule.id, op=matched_rule.action.operation.value,
          caller_spiffe_id=state.get("spiffe_id", ""),
          original_len=original_len, new_len=new_len,
          latency_ms=round(elapsed_ms, 2))
      metrics.requests_total.add(1, {"outcome": "success"})
      metrics.amend_latency_seconds.record(elapsed_ms / 1000)

    body_resp = service_pb2.BodyResponse()
    body_resp.response.body_mutation.body = mutated_body
    body_resp.response.header_mutation.set_headers.append(HeaderValueOption(
        header=HeaderValue(key="content-length",
                            raw_value=str(len(mutated_body)).encode("utf-8")),
        append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD))
    return body_resp

  # ----------------------------------------------------------------- impl

  def _mutate(self, raw_body: bytes, rule: Rule,
              state: dict) -> tuple[bytes, int, int]:
    if len(raw_body) > self.max_request_body_bytes:
      raise BodyTooLargeError(
          f"body size {len(raw_body)} exceeds "
          f"MAX_REQUEST_BODY_BYTES={self.max_request_body_bytes}")
    try:
      payload = json.loads(raw_body)
    except ValueError as exc:
      raise ValueError(f"request body is not valid JSON: {exc}") from exc

    payload, parts = _locate_system_instruction(payload)
    text_part = next(p for p in parts if isinstance(p, dict) and "text" in p)

    original_prompt = text_part["text"]
    template_vars = {
        "caller_spiffe_id": state.get("spiffe_id", ""),
        "host": state.get("host", ""),
        "path": state.get("path", ""),
    }
    new_prompt = apply_action(rule.action, original_prompt, template_vars)
    text_part["text"] = new_prompt

    new_body = json.dumps(payload).encode("utf-8")
    return new_body, len(original_prompt), len(new_prompt)


if __name__ == "__main__":
  configure_json_logging(os.getenv("LOG_LEVEL", "INFO"))
  PromptAmenderCallout(disable_tls=True).run()
