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

"""Pure unit tests for the Prompt-Amender rule engine: selector matching,
mutation operations, and ruleset validation. No gRPC server, no network.

Lives in the shared `extproc/tests/` tree (flat `<name>_test.py` naming),
not under `extproc/example/prompt_amender/`, so `pytest extproc/tests/`
picks it up along with every other example's tests.
"""
import unittest

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
