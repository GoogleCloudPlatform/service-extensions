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
configured mutation `action` is applied to the request's system-instruction
text during the body phase.

Glob semantics: matching uses `fnmatch.fnmatchcase`, so `*` is a normal
shell-style wildcard and DOES cross `/` (unlike a URL-routing glob library).
`principalSet://agents.example/*` therefore matches
`principalSet://agents.example/support/agent-1` (crossing the `/` before
`support`), not just a single path segment. Write selectors with this in
mind -- a trailing `/*` matches everything under that prefix, however deep.
"""
import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jinja2 import StrictUndefined, Template, TemplateError
from jinja2.sandbox import SandboxedEnvironment

# Rules are sourced from GCS or git -- semi-trusted config, not application
# code. A plain jinja2.Environment lets anyone who can write rules.yaml
# achieve remote code execution in the callout via SSTI (e.g.
# `{{ ''.__class__.__mro__[1].__subclasses__() }}`). SandboxedEnvironment
# blocks attribute access to unsafe internals while still allowing the
# `template` action's legitimate use of `original_prompt`/`caller_spiffe_id`
# substitution.
_jinja_env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)

# The gateway's architecture doc says it injects `spiffe://...` identities,
# but samples and some deployments use `principalSet://...` (the IAM
# workload-identity-pool principal form). Selectors are written in one
# scheme; incoming headers may arrive in the other. Normalize both to the
# `principalSet://` form before matching so a rule written against either
# scheme still matches. If your gateway uses a different scheme entirely,
# extend this function rather than relying on scheme-mismatched selectors
# silently never matching.
_SPIFFE_PREFIX = "spiffe://"
_PRINCIPAL_SET_PREFIX = "principalSet://"


def canonical_identity(value: str) -> str:
  """Normalizes an identity string to the `principalSet://` scheme."""
  if value.startswith(_SPIFFE_PREFIX):
    return _PRINCIPAL_SET_PREFIX + value[len(_SPIFFE_PREFIX):]
  return value


def locate_system_instruction(payload: Any) -> tuple[dict, list]:
  """Finds (or creates) the system-instruction object and its parts list
  in a decoded JSON request body, and returns `(payload, parts)`.

  Accepts both the canonical proto3 JSON spelling `systemInstruction` (what
  every official Vertex/Gemini SDK sends) and the legacy `system_instruction`
  spelling. If the request has neither, or has one in a shape this function
  doesn't recognize (not an object, `parts` not a list, no part with a
  string `text`), a fresh `systemInstruction` object with one empty text
  part is created and used instead of raising -- this function never
  assumes the caller-supplied JSON matches any particular shape beyond
  being a JSON object at the top level, since a malformed or adversarial
  request body must fail open, not crash the request.
  """
  if not isinstance(payload, dict):
    raise ValueError("request body JSON must be an object")

  key = ("systemInstruction" if "systemInstruction" in payload
         else "system_instruction")
  si = payload.get(key)
  if not isinstance(si, dict):
    si = {"parts": [{"text": ""}]}
    payload["systemInstruction"] = si
    key = "systemInstruction"

  parts = si.get("parts")
  if not isinstance(parts, list):
    parts = []
    si["parts"] = parts

  text_part = next(
      (p for p in parts
       if isinstance(p, dict) and isinstance(p.get("text"), str)),
      None)
  if text_part is None:
    text_part = {"text": ""}
    parts.append(text_part)

  return payload, parts


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
    if self.identity and not fnmatch.fnmatchcase(
        canonical_identity(spiffe_id), canonical_identity(self.identity)):
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
  template: str = ""   # for template (source text, kept for introspection)
  compiled_template: Optional[Template] = None  # for template, parsed once


@dataclass
class Rule:
  id: str
  description: str
  selectors: Selector
  action: Action


@dataclass
class Ruleset:
  rules: list[Rule] = field(default_factory=list)

  def find_match(self, spiffe_id: str, host: str, path: str) -> Optional[Rule]:
    """First-match-wins, in declaration order."""
    for rule in self.rules:
      if rule.selectors.matches(spiffe_id, host, path):
        return rule
    return None


def parse_ruleset(raw: Any) -> Ruleset:
  if not isinstance(raw, dict) or "rules" not in raw:
    raise RulesetValidationError(
        "top-level YAML must be a mapping with a `rules` key")

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
      raise RulesetValidationError(
          f"rules[{i}] missing required string field `id`")
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
          f"rule '{rule_id}' has no selectors -- refusing to load a rule "
          "that matches all traffic")

    action_raw = entry.get("action")
    if not isinstance(action_raw, dict) or "operation" not in action_raw:
      raise RulesetValidationError(
          f"rule '{rule_id}' missing required `action.operation`")
    try:
      op = Operation(action_raw["operation"])
    except ValueError as exc:
      raise RulesetValidationError(
          f"rule '{rule_id}' has unknown action.operation: "
          f"{action_raw['operation']!r}") from exc

    if op in (Operation.PREPEND, Operation.APPEND, Operation.REPLACE):
      text = action_raw.get("text")
      if not isinstance(text, str):
        raise RulesetValidationError(
            f"rule '{rule_id}' action requires string `text`")
      action = Action(operation=op, text=text)
    else:  # TEMPLATE
      template = action_raw.get("template")
      if not isinstance(template, str):
        raise RulesetValidationError(
            f"rule '{rule_id}' action requires string `template`")
      try:
        compiled = _jinja_env.from_string(template)
      except TemplateError as exc:
        raise RulesetValidationError(
            f"rule '{rule_id}' has invalid Jinja2 template: {exc}") from exc
      action = Action(
          operation=op, template=template, compiled_template=compiled)

    parsed_rules.append(Rule(
        id=rule_id, description=entry.get("description", ""),
        selectors=selectors, action=action))

  return Ruleset(rules=parsed_rules)


def apply_action(
    action: Action, original_prompt: str, template_vars: dict[str, Any],
) -> str:
  """Applies a rule's mutation to the original system-instruction text.

  `template_vars` always includes `original_prompt`, `caller_spiffe_id`,
  `host`, `path`. For the `template` operation, this renders
  `action.compiled_template` -- parsed once by `parse_ruleset` rather than
  recompiled on every request -- falling back to compiling `action.template`
  on the spot only for an `Action` built directly (e.g. in tests) rather
  than through `parse_ruleset`.
  """
  if action.operation == Operation.PREPEND:
    return f"{action.text}\n\n{original_prompt}"
  if action.operation == Operation.APPEND:
    return f"{original_prompt}\n\n{action.text}"
  if action.operation == Operation.REPLACE:
    return action.text
  if action.operation == Operation.TEMPLATE:
    try:
      compiled = action.compiled_template or _jinja_env.from_string(
          action.template)
      merged_vars = {"original_prompt": original_prompt, **template_vars}
      return compiled.render(**merged_vars)
    except TemplateError as exc:
      raise TemplateRenderError(str(exc)) from exc
  raise TemplateRenderError(f"unhandled operation: {action.operation}")
