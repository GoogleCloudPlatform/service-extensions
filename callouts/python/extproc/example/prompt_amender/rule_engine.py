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

"""Rule engine for the Prompt-Amender callout.

Deliberately dependency-light (stdlib `fnmatch` + `jinja2` only) and free of
any gRPC/Envoy imports, so it can be unit tested without a running callout
server -- matching the testing style used across this collection.

Rules are matched by three selectors -- `identity` (SPIFFE ID / principal
set, UNIX-glob), `host` (:authority header, glob), and `path` (:path
header, glob) -- against every request in the header phase. On match, the
configured mutation `action` is applied to the request's
`system_instruction.parts[].text` field during the body phase.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import fnmatch

from jinja2 import Environment, StrictUndefined, TemplateError

_jinja_env = Environment(undefined=StrictUndefined, autoescape=False)


class RulesetValidationError(Exception):
    pass


class TemplateRenderError(Exception):
    pass


class Operation(str, Enum):
    PREPEND = "prepend"
    APPEND = "append"
    REPLACE = "replace"
    TEMPLATE = "template"


@dataclass
class Selector:
    identity: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None

    def matches(self, spiffe_id: str, host: str, path: str) -> bool:
        if self.identity and not fnmatch.fnmatchcase(spiffe_id, self.identity):
            return False
        if self.host and not fnmatch.fnmatchcase(host, self.host):
            return False
        if self.path and not fnmatch.fnmatchcase(path, self.path):
            return False
        return True


@dataclass
class Action:
    operation: Operation
    text: str = ""       # for prepend/append/replace
    template: str = ""   # for template


@dataclass
class Rule:
    id: str
    description: str
    selectors: Selector
    action: Action


@dataclass
class Ruleset:
    rules: list = field(default_factory=list)

    def find_match(self, spiffe_id: str, host: str, path: str) -> Optional[Rule]:
        """First-match-wins, in declaration order."""
        for rule in self.rules:
            if rule.selectors.matches(spiffe_id, host, path):
                return rule
        return None


def parse_ruleset(raw: Any) -> Ruleset:
    if not isinstance(raw, dict) or "rules" not in raw:
        raise RulesetValidationError("top-level YAML must be a mapping with a `rules` key")

    rules_raw = raw["rules"]
    if not isinstance(rules_raw, list):
        raise RulesetValidationError("`rules` must be a list")

    parsed_rules: list[Rule] = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(rules_raw):
        if not isinstance(entry, dict):
            raise RulesetValidationError(f"rules[{i}] must be a mapping")

        rule_id = entry.get("id")
        if not rule_id or not isinstance(rule_id, str):
            raise RulesetValidationError(f"rules[{i}] missing required string field `id`")
        if rule_id in seen_ids:
            raise RulesetValidationError(f"duplicate rule id: {rule_id}")
        seen_ids.add(rule_id)

        selectors_raw = entry.get("selectors", {})
        if not isinstance(selectors_raw, dict):
            raise RulesetValidationError(f"rules[{i}].selectors must be a mapping")
        selectors = Selector(
            identity=selectors_raw.get("identity"),
            host=selectors_raw.get("host"),
            path=selectors_raw.get("path"),
        )
        if not any([selectors.identity, selectors.host, selectors.path]):
            raise RulesetValidationError(
                f"rule '{rule_id}' has no selectors -- refusing to load a rule that matches all traffic"
            )

        action_raw = entry.get("action")
        if not isinstance(action_raw, dict) or "operation" not in action_raw:
            raise RulesetValidationError(f"rule '{rule_id}' missing required `action.operation`")
        try:
            op = Operation(action_raw["operation"])
        except ValueError as exc:
            raise RulesetValidationError(
                f"rule '{rule_id}' has unknown action.operation: {action_raw['operation']!r}"
            ) from exc

        if op in (Operation.PREPEND, Operation.APPEND, Operation.REPLACE):
            text = action_raw.get("text")
            if not isinstance(text, str):
                raise RulesetValidationError(f"rule '{rule_id}' action requires string `text`")
            action = Action(operation=op, text=text)
        else:  # TEMPLATE
            template = action_raw.get("template")
            if not isinstance(template, str):
                raise RulesetValidationError(f"rule '{rule_id}' action requires string `template`")
            try:
                _jinja_env.from_string(template)
            except TemplateError as exc:
                raise RulesetValidationError(f"rule '{rule_id}' has invalid Jinja2 template: {exc}") from exc
            action = Action(operation=op, template=template)

        parsed_rules.append(
            Rule(id=rule_id, description=entry.get("description", ""), selectors=selectors, action=action)
        )

    return Ruleset(rules=parsed_rules)


def apply_action(action: Action, original_prompt: str, template_vars: dict) -> str:
    """Applies a rule's mutation to the original system-instruction text.

    `template_vars` always includes `original_prompt`, `caller_spiffe_id`,
    `host`, `path`.
    """
    if action.operation == Operation.PREPEND:
        return f"{action.text}\n\n{original_prompt}"
    if action.operation == Operation.APPEND:
        return f"{original_prompt}\n\n{action.text}"
    if action.operation == Operation.REPLACE:
        return action.text
    if action.operation == Operation.TEMPLATE:
        try:
            tmpl = _jinja_env.from_string(action.template)
            merged_vars = {"original_prompt": original_prompt, **template_vars}
            return tmpl.render(**merged_vars)
        except TemplateError as exc:
            raise TemplateRenderError(str(exc)) from exc
    raise TemplateRenderError(f"unhandled operation: {action.operation}")
