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

"""Pure unit tests for the Prompt-Amender rule engine and body-chunk
assembly state machine. No gRPC server, no network.

Lives in the shared `extproc/tests/` tree (flat `<name>_test.py` naming),
not under `extproc/example/prompt_amender/`, so `pytest extproc/tests/`
picks it up along with every other example's tests.
"""
import unittest

from extproc.example.prompt_amender.body_assembly import (
    BodyAssemblyState, BodyTooLargeError, ChunkAction, process_chunk)
from extproc.example.prompt_amender.rule_engine import (
    Action, Operation, RulesetValidationError, Selector, apply_action,
    canonical_identity, locate_system_instruction, parse_ruleset)


class TestSelectorMatching(unittest.TestCase):

  def test_identity_glob_match(self):
    sel = Selector(identity="principalSet://agents.global.org-123/*")
    self.assertTrue(sel.matches(
        "principalSet://agents.global.org-123/support/agent-1", "", ""))
    self.assertFalse(sel.matches(
        "principalSet://agents.global.org-999/support/agent-1", "", ""))

  def test_all_selectors_must_match(self):
    sel = Selector(
        identity="spiffe://*", host="api.example.com",
        path="/v1/generateContent")
    self.assertTrue(sel.matches(
        "spiffe://foo", "api.example.com", "/v1/generateContent"))
    self.assertFalse(sel.matches(
        "spiffe://foo", "other.example.com", "/v1/generateContent"))

  def test_no_selectors_set_matches_everything(self):
    sel = Selector()
    self.assertTrue(sel.matches("anything", "anything", "anything"))

  def test_spiffe_header_matches_principal_set_selector(self):
    # The gateway may inject `spiffe://...` while the rule is written
    # against `principalSet://...` (or vice versa). Both must match.
    sel = Selector(identity="principalSet://agents.example.org/support/*")
    self.assertTrue(sel.matches(
        "spiffe://agents.example.org/support/agent-1", "", ""))

  def test_principal_set_header_matches_spiffe_selector(self):
    sel = Selector(identity="spiffe://agents.example.org/support/*")
    self.assertTrue(sel.matches(
        "principalSet://agents.example.org/support/agent-1", "", ""))

  def test_canonical_identity_normalizes_spiffe_scheme(self):
    self.assertEqual(
        canonical_identity("spiffe://agents.example.org/x"),
        "principalSet://agents.example.org/x")
    self.assertEqual(
        canonical_identity("principalSet://agents.example.org/x"),
        "principalSet://agents.example.org/x")


class TestMutationOperations(unittest.TestCase):

  def test_prepend(self):
    action = Action(operation=Operation.PREPEND, text="PREFIX")
    self.assertEqual(
        apply_action(action, "original", {}), "PREFIX\n\noriginal")

  def test_append(self):
    action = Action(operation=Operation.APPEND, text="SUFFIX")
    self.assertEqual(
        apply_action(action, "original", {}), "original\n\nSUFFIX")

  def test_replace(self):
    action = Action(operation=Operation.REPLACE, text="NEW TEXT")
    self.assertEqual(apply_action(action, "original", {}), "NEW TEXT")

  def test_template_merges_vars(self):
    action = Action(
        operation=Operation.TEMPLATE,
        template="{{ original_prompt }} caller={{ caller_spiffe_id }}")
    result = apply_action(
        action, "You are a bot.", {"caller_spiffe_id": "spiffe://x"})
    self.assertEqual(result, "You are a bot. caller=spiffe://x")

  def test_template_sandbox_blocks_unsafe_attribute_access(self):
    # SandboxedEnvironment must reject SSTI attempts against a
    # semi-trusted template sourced from GCS/git.
    action = Action(
        operation=Operation.TEMPLATE,
        template="{{ ''.__class__.__mro__[1].__subclasses__() }}")
    with self.assertRaises(Exception):
      apply_action(action, "original", {})


class TestLocateSystemInstruction(unittest.TestCase):
  """Covers the shapes a malformed or adversarial request body can take.
  None of these should raise -- a request body that doesn't match the
  expected shape must fail open, not crash the request."""

  def test_non_dict_payload_raises_value_error(self):
    # The one case that's still an error: the top-level body isn't even a
    # JSON object, e.g. a bare array or string. _mutate's caller treats
    # ValueError as a fail-open case.
    with self.assertRaises(ValueError):
      locate_system_instruction(["not", "an", "object"])
    with self.assertRaises(ValueError):
      locate_system_instruction("also not an object")

  def test_system_instruction_not_an_object(self):
    payload, parts = locate_system_instruction(
        {"systemInstruction": "a string, not an object"})
    self.assertEqual(len(parts), 1)
    self.assertEqual(parts[0]["text"], "")
    self.assertIs(payload["systemInstruction"]["parts"], parts)

  def test_text_field_not_a_string_int(self):
    _, parts = locate_system_instruction(
        {"systemInstruction": {"parts": [{"text": 123}]}})
    # The malformed part is left alone; a usable text part is added
    # alongside it rather than coercing 123 into a string.
    self.assertTrue(
        any(isinstance(p.get("text"), str) for p in parts))

  def test_text_field_not_a_string_none(self):
    _, parts = locate_system_instruction(
        {"systemInstruction": {"parts": [{"text": None}]}})
    self.assertTrue(
        any(isinstance(p.get("text"), str) for p in parts))

  def test_text_field_not_a_string_list(self):
    # Regression: a list `text` value must never be silently accepted and
    # str()-formatted into the prompt.
    _, parts = locate_system_instruction(
        {"systemInstruction": {"parts": [{"text": ["a"]}]}})
    usable = [p for p in parts if isinstance(p.get("text"), str)]
    self.assertEqual(len(usable), 1)
    self.assertEqual(usable[0]["text"], "")

  def test_missing_system_instruction_inserts_empty_one(self):
    payload, parts = locate_system_instruction({"contents": []})
    self.assertEqual(len(parts), 1)
    self.assertEqual(parts[0]["text"], "")
    self.assertIn("systemInstruction", payload)


class TestTemplateCompiledOnce(unittest.TestCase):

  def test_parsed_ruleset_reuses_compiled_template(self):
    raw = {"rules": [{
        "id": "r1", "selectors": {"host": "*"},
        "action": {
            "operation": "template", "template": "{{ original_prompt }}"},
    }]}
    ruleset = parse_ruleset(raw)
    action = ruleset.rules[0].action
    self.assertIsNotNone(action.compiled_template)
    result = apply_action(action, "hi", {})
    self.assertEqual(result, "hi")


class TestBodyAssembly(unittest.TestCase):
  """Covers the chunk withhold/emit/fail-open/pass-through transitions in
  body_assembly.process_chunk -- the state machine that exists specifically
  because a naive "accumulate and mutate the last chunk" implementation
  corrupts a multi-chunk request (Envoy forwards intermediate chunks
  immediately; a bare pass-through does not withhold them)."""

  def test_single_chunk_end_of_stream_emits_mutated_directly(self):
    # The common case: mode_override honored, one BUFFERED chunk.
    state = BodyAssemblyState()
    result = process_chunk(
        state, b"original", end_of_stream=True, max_body_bytes=1000,
        fail_open=True, mutate=lambda buf: (b"mutated:" + buf, 8, 16))
    self.assertEqual(result.action, ChunkAction.EMIT_MUTATED)
    self.assertEqual(result.body, b"mutated:original")

  def test_multi_chunk_delivery_withholds_then_emits_once(self):
    # The regression this state machine exists to prevent: multiple
    # chunks must produce exactly one emitted (mutated) body, not one
    # withheld response plus a second response that only replaces the
    # final chunk.
    state = BodyAssemblyState()
    calls = []

    def mutate(buf):
      calls.append(buf)
      return b"MUTATED", len(buf), 7

    r1 = process_chunk(
        state, b"chunk-one-", end_of_stream=False, max_body_bytes=1000,
        fail_open=True, mutate=mutate)
    self.assertEqual(r1.action, ChunkAction.WITHHOLD)

    r2 = process_chunk(
        state, b"chunk-two", end_of_stream=False, max_body_bytes=1000,
        fail_open=True, mutate=mutate)
    self.assertEqual(r2.action, ChunkAction.WITHHOLD)

    r3 = process_chunk(
        state, b"-final", end_of_stream=True, max_body_bytes=1000,
        fail_open=True, mutate=mutate)
    self.assertEqual(r3.action, ChunkAction.EMIT_MUTATED)
    self.assertEqual(r3.body, b"MUTATED")
    # mutate() is called exactly once, with every chunk concatenated --
    # not once per chunk, and not with any single chunk in isolation.
    self.assertEqual(calls, [b"chunk-one-chunk-two-final"])

  def test_mid_stream_failure_fail_open_emits_original_intact(self):
    # If earlier chunks were withheld and the final chunk's amendment
    # fails, fail-open must reconstruct and emit the FULL original body,
    # not just the final chunk -- a bare pass-through here would truncate
    # the request to whatever chunk happened to fail on.
    state = BodyAssemblyState()

    def mutate(buf):
      raise ValueError("not valid JSON")

    r1 = process_chunk(
        state, b"{not valid", end_of_stream=False, max_body_bytes=1000,
        fail_open=True, mutate=mutate)
    self.assertEqual(r1.action, ChunkAction.WITHHOLD)

    r2 = process_chunk(
        state, b" json}", end_of_stream=True, max_body_bytes=1000,
        fail_open=True, mutate=mutate)
    self.assertEqual(r2.action, ChunkAction.EMIT_ORIGINAL)
    self.assertEqual(r2.body, b"{not valid json}")
    self.assertIsInstance(r2.error, ValueError)
    self.assertTrue(state.failed)

  def test_mid_stream_failure_fail_closed_rejects(self):
    state = BodyAssemblyState()

    def mutate(buf):
      raise ValueError("not valid JSON")

    result = process_chunk(
        state, b"bad json", end_of_stream=True, max_body_bytes=1000,
        fail_open=False, mutate=mutate)
    self.assertEqual(result.action, ChunkAction.REJECT)

  def test_oversized_body_fail_open_emits_original_so_far(self):
    state = BodyAssemblyState()
    result = process_chunk(
        state, b"way too long", end_of_stream=False, max_body_bytes=5,
        fail_open=True, mutate=lambda buf: (buf, 0, 0))
    self.assertEqual(result.action, ChunkAction.EMIT_ORIGINAL)
    self.assertEqual(result.body, b"way too long")
    self.assertIsInstance(result.error, BodyTooLargeError)
    self.assertTrue(state.failed)

  def test_oversized_body_fail_closed_rejects(self):
    state = BodyAssemblyState()
    result = process_chunk(
        state, b"way too long", end_of_stream=False, max_body_bytes=5,
        fail_open=False, mutate=lambda buf: (buf, 0, 0))
    self.assertEqual(result.action, ChunkAction.REJECT)

  def test_chunks_after_failure_pass_through_untouched(self):
    # Once a stream has failed (and that failure already emitted a
    # reconstruction or rejection covering everything up to that point),
    # every later chunk of the same request must be forwarded raw --
    # nothing further should be withheld or re-processed.
    state = BodyAssemblyState()
    process_chunk(
        state, b"x" * 10, end_of_stream=False, max_body_bytes=5,
        fail_open=True, mutate=lambda buf: (buf, 0, 0))
    self.assertTrue(state.failed)

    later = process_chunk(
        state, b"more-data", end_of_stream=False, max_body_bytes=5,
        fail_open=True, mutate=lambda buf: (buf, 0, 0))
    self.assertEqual(later.action, ChunkAction.PASS_THROUGH)

    final = process_chunk(
        state, b"final-chunk", end_of_stream=True, max_body_bytes=5,
        fail_open=True, mutate=lambda buf: (buf, 0, 0))
    self.assertEqual(final.action, ChunkAction.PASS_THROUGH)

  def test_unexpected_exception_type_still_triggers_fail_open(self):
    # The except clause in process_chunk is deliberately broad: an
    # exception type nobody anticipated must still fail open rather than
    # propagate and abort the gRPC stream.
    state = BodyAssemblyState()

    def mutate(buf):
      raise RuntimeError("something nobody anticipated")

    result = process_chunk(
        state, b"data", end_of_stream=True, max_body_bytes=1000,
        fail_open=True, mutate=mutate)
    self.assertEqual(result.action, ChunkAction.EMIT_ORIGINAL)
    self.assertEqual(result.body, b"data")


class TestRulesetValidation(unittest.TestCase):

  def test_valid_ruleset_parses(self):
    raw = {"rules": [{
        "id": "r1", "selectors": {"host": "api.example.com"},
        "action": {"operation": "append", "text": "hi"},
    }]}
    ruleset = parse_ruleset(raw)
    self.assertEqual(len(ruleset.rules), 1)
    self.assertEqual(ruleset.rules[0].id, "r1")

  def test_rejects_rule_with_no_selectors(self):
    raw = {"rules": [{
        "id": "r1", "selectors": {},
        "action": {"operation": "append", "text": "hi"},
    }]}
    with self.assertRaises(RulesetValidationError):
      parse_ruleset(raw)

  def test_rejects_duplicate_ids(self):
    rule = {
        "id": "dup", "selectors": {"host": "*"},
        "action": {"operation": "append", "text": "x"},
    }
    raw = {"rules": [rule, dict(rule)]}
    with self.assertRaises(RulesetValidationError):
      parse_ruleset(raw)

  def test_rejects_invalid_template_syntax(self):
    raw = {"rules": [{
        "id": "bad-template", "selectors": {"host": "*"},
        "action": {"operation": "template", "template": "{{ unclosed"},
    }]}
    with self.assertRaises(RulesetValidationError):
      parse_ruleset(raw)

  def test_first_match_wins(self):
    raw = {"rules": [
        {
            "id": "r1", "selectors": {"host": "api.example.com"},
            "action": {"operation": "replace", "text": "first"},
        },
        {
            "id": "r2", "selectors": {"host": "*"},
            "action": {"operation": "replace", "text": "second"},
        },
    ]}
    ruleset = parse_ruleset(raw)
    match = ruleset.find_match("", "api.example.com", "")
    self.assertEqual(match.id, "r1")


if __name__ == "__main__":
  unittest.main()
