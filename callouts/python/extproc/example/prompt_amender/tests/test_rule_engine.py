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

"""Pure unit tests for the rule engine: selector matching, mutation
operations, and ruleset validation. No gRPC server, no network."""
import unittest

from rule_engine import (
    Action, Operation, Selector, apply_action, parse_ruleset, RulesetValidationError,
)


class TestSelectorMatching(unittest.TestCase):
    def test_identity_glob_match(self):
        sel = Selector(identity="principalSet://agents.global.org-123/*")
        self.assertTrue(sel.matches("principalSet://agents.global.org-123/support/agent-1", "", ""))
        self.assertFalse(sel.matches("principalSet://agents.global.org-999/support/agent-1", "", ""))

    def test_all_selectors_must_match(self):
        sel = Selector(identity="spiffe://*", host="api.example.com", path="/v1/generateContent")
        self.assertTrue(sel.matches("spiffe://foo", "api.example.com", "/v1/generateContent"))
        self.assertFalse(sel.matches("spiffe://foo", "other.example.com", "/v1/generateContent"))

    def test_no_selectors_set_matches_everything(self):
        sel = Selector()
        self.assertTrue(sel.matches("anything", "anything", "anything"))


class TestMutationOperations(unittest.TestCase):
    def test_prepend(self):
        action = Action(operation=Operation.PREPEND, text="PREFIX")
        self.assertEqual(apply_action(action, "original", {}), "PREFIX\n\noriginal")

    def test_append(self):
        action = Action(operation=Operation.APPEND, text="SUFFIX")
        self.assertEqual(apply_action(action, "original", {}), "original\n\nSUFFIX")

    def test_replace(self):
        action = Action(operation=Operation.REPLACE, text="NEW TEXT")
        self.assertEqual(apply_action(action, "original", {}), "NEW TEXT")

    def test_template_merges_vars(self):
        action = Action(operation=Operation.TEMPLATE, template="{{ original_prompt }} caller={{ caller_spiffe_id }}")
        result = apply_action(action, "You are a bot.", {"caller_spiffe_id": "spiffe://x"})
        self.assertEqual(result, "You are a bot. caller=spiffe://x")


class TestRulesetValidation(unittest.TestCase):
    def test_valid_ruleset_parses(self):
        raw = {"rules": [{"id": "r1", "selectors": {"host": "api.example.com"},
                           "action": {"operation": "append", "text": "hi"}}]}
        ruleset = parse_ruleset(raw)
        self.assertEqual(len(ruleset.rules), 1)
        self.assertEqual(ruleset.rules[0].id, "r1")

    def test_rejects_rule_with_no_selectors(self):
        raw = {"rules": [{"id": "r1", "selectors": {}, "action": {"operation": "append", "text": "hi"}}]}
        with self.assertRaises(RulesetValidationError):
            parse_ruleset(raw)

    def test_rejects_duplicate_ids(self):
        rule = {"id": "dup", "selectors": {"host": "*"}, "action": {"operation": "append", "text": "x"}}
        raw = {"rules": [rule, dict(rule)]}
        with self.assertRaises(RulesetValidationError):
            parse_ruleset(raw)

    def test_rejects_invalid_template_syntax(self):
        raw = {"rules": [{"id": "bad-template", "selectors": {"host": "*"},
                           "action": {"operation": "template", "template": "{{ unclosed"}}]}
        with self.assertRaises(RulesetValidationError):
            parse_ruleset(raw)

    def test_first_match_wins(self):
        raw = {"rules": [
            {"id": "r1", "selectors": {"host": "api.example.com"}, "action": {"operation": "replace", "text": "first"}},
            {"id": "r2", "selectors": {"host": "*"}, "action": {"operation": "replace", "text": "second"}},
        ]}
        ruleset = parse_ruleset(raw)
        match = ruleset.find_match("", "api.example.com", "")
        self.assertEqual(match.id, "r1")


if __name__ == "__main__":
    unittest.main()
