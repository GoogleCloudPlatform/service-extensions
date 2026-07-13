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
ruleset; on a match it mutates the request's `system_instruction.parts[].text`
field before forwarding to the LLM backend (e.g. Vertex AI).

Two-phase design, mirroring the Envoy processing model other examples in
this collection use:

  Header phase (`on_request_headers`): extract the caller's SPIFFE ID
  (from the trusted `x-spiffe-id` header the Agent Gateway injects after
  mTLS/SVID validation), `:authority`, and `:path`; evaluate against the
  active ruleset. On a match, override `mode_override.request_body_mode` to
  `BUFFERED` so the gateway streams us the body; on no match, override it
  to `NONE` so we never pay body-buffering latency for traffic the ruleset
  doesn't care about. This is the same technique the litellm_gateway
  example uses (there, on the *response* body mode; here, on *request*).

  Body phase (`on_request_body`): parse the buffered JSON body, locate
  `system_instruction.parts[].text`, apply the matched rule's mutation
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
  * structured logging that never includes raw prompt text (only rule_id,
    op, caller_spiffe_id, original_len, new_len, latency_ms)
"""

import json
import logging
import os
import time

from grpc import ServicerContext

from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import ProcessingMode
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.service import callout_server
from extproc.service import callout_tools

from rule_engine import Rule, TemplateRenderError, apply_action
from config_sources import HotReloadingRuleProvider, build_config_source

SPIFFE_HEADER = "x-spiffe-id"
AUTHORITY_HEADER = ":authority"
PATH_HEADER = ":path"


class BodyTooLargeError(Exception):
    pass


class SystemInstructionNotFoundError(Exception):
    pass


def _state(context: ServicerContext) -> dict:
    state = getattr(context, "_prompt_amender_state", None)
    if state is None:
        state = {}
        context._prompt_amender_state = state
    return state


class PromptAmenderCallout(callout_server.CalloutServer):
    """Ext_proc callout that mutates LLM system instructions in-transit."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fail_open = os.getenv("FAIL_OPEN", "true").lower() == "true"
        self.max_request_body_bytes = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(4 * 1024 * 1024)))

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
            logger=logging.getLogger("prompt_amender.rules"),
        )
        self.rule_provider.load_initial()  # must succeed at startup
        self.rule_provider.start_background_polling()
        logging.info("Loaded %d prompt-amender rule(s)", len(self.rule_provider.current().rules))

    # ------------------------------------------------------------------ phases

    def on_request_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.ProcessingResponse | None:
        spiffe_id, host, path = "", "", ""
        for h in headers.headers.headers:
            key = h.key.lower()
            value = (h.raw_value or h.value.encode("utf-8")).decode("utf-8", errors="replace")
            if key == SPIFFE_HEADER:
                spiffe_id = value
            elif key in (AUTHORITY_HEADER, "host"):
                host = value
            elif key == PATH_HEADER:
                path = value

        ruleset = self.rule_provider.current()
        matched_rule = ruleset.find_match(spiffe_id, host, path)

        state = _state(context)
        state["matched_rule"] = matched_rule
        state["spiffe_id"] = spiffe_id
        state["host"] = host
        state["path"] = path

        resp = service_pb2.ProcessingResponse()
        mode = ProcessingMode()
        if matched_rule is None:
            # No rule cares about this request -- skip body buffering
            # entirely so unmatched traffic pays near-zero latency tax.
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
            return None  # shouldn't happen (mode_override skips body on no-match), but pass through safely

        start = time.monotonic()
        try:
            mutated_body, original_len, new_len = self._mutate(body.body, matched_rule, state)
        except (BodyTooLargeError, SystemInstructionNotFoundError, TemplateRenderError, ValueError) as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logging.error(
                "prompt amendment failed; passing request through unmodified: "
                "rule_id=%s op=%s caller_spiffe_id=%s error=%s latency_ms=%.2f",
                matched_rule.id, matched_rule.action.operation.value,
                state.get("spiffe_id", ""), exc, elapsed_ms,
            )
            if self.fail_open:
                return None
            return callout_tools.header_immediate_response(StatusCode.InternalServerError)

        elapsed_ms = (time.monotonic() - start) * 1000
        logging.info(
            "prompt amendment applied: rule_id=%s op=%s caller_spiffe_id=%s "
            "original_len=%d new_len=%d latency_ms=%.2f",
            matched_rule.id, matched_rule.action.operation.value,
            state.get("spiffe_id", ""), original_len, new_len, elapsed_ms,
        )

        body_resp = service_pb2.BodyResponse()
        body_resp.response.body_mutation.body = mutated_body
        body_resp.response.header_mutation.set_headers.append(
            HeaderValueOption(
                header=HeaderValue(key="content-length", raw_value=str(len(mutated_body)).encode("utf-8")),
                append_action=HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
            ))
        return body_resp

    # ------------------------------------------------------------------- impl

    def _mutate(self, raw_body: bytes, rule: Rule, state: dict) -> tuple[bytes, int, int]:
        if len(raw_body) > self.max_request_body_bytes:
            raise BodyTooLargeError(
                f"body size {len(raw_body)} exceeds MAX_REQUEST_BODY_BYTES={self.max_request_body_bytes}"
            )
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"request body is not valid JSON: {exc}") from exc

        parts = (payload.get("system_instruction") or {}).get("parts")
        if not isinstance(parts, list) or not parts:
            raise SystemInstructionNotFoundError("system_instruction.parts[] not found or empty")

        text_part = next((p for p in parts if isinstance(p, dict) and "text" in p), None)
        if text_part is None:
            raise SystemInstructionNotFoundError("no part with a `text` field found")

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
    logging.basicConfig(level=logging.INFO)
    PromptAmenderCallout(disable_tls=True).run()
