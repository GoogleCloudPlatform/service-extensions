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

"""Optional YAML config for the gateway, modeled on LiteLLM's config.yaml.

Env-gated: inert unless GATEWAY_CONFIG points at a YAML file. Section names
mirror the LiteLLM proxy config so a reader familiar with LiteLLM recognizes
the knobs:

  router_settings:    routing-strategy config consumed by routing.configure()
                      (model_group_alias matches LiteLLM's key of the same
                      name; the other three configure this sample's
                      strategies).
  litellm_settings:   redact_user_api_key_info, as in LiteLLM.
  general_settings:   quota_fail_open (this sample's name for LiteLLM's
                      fail-open vs fail_closed_budget_enforcement choice).

A deployment without a config file gets the built-in defaults, so the file
is a customization point, not a requirement.
"""

import logging
import os
from typing import Any, NamedTuple, Optional

import yaml


class RoutingSettings(NamedTuple):
    model_group_alias: dict[str, str]
    tag_rules: dict[tuple[str, str], str]
    weighted_groups: dict[str, list[tuple[str, int]]]
    shuffle_groups: dict[str, list[str]]


class TelemetrySettings(NamedTuple):
    redact_user_api_key_info: bool


class QuotaSettings(NamedTuple):
    fail_open: bool


_config: dict[str, Any] = {}


def load() -> None:
    """Load the YAML file named by GATEWAY_CONFIG. No-op when unset.

    A bad path or a YAML syntax error is logged as a warning and leaves the
    config empty (routing disabled, other defaults apply).
    """
    path = os.getenv("GATEWAY_CONFIG", "")
    if not path:
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            _load_dict(yaml.safe_load(f) or {})
    except Exception as e:
        logging.warning("Failed to load GATEWAY_CONFIG %s: %s", path, e)
        _load_dict({})
        return
    logging.info("Gateway config loaded from %s", path)


def _load_dict(cfg: dict[str, Any]) -> None:
    """Install a parsed config dict. Also a test hook."""
    global _config
    _config = cfg or {}


def _reset() -> None:
    """Test hook: drop any loaded config."""
    global _config
    _config = {}


def routing_settings() -> Optional[RoutingSettings]:
    """Parsed router_settings, or None to keep the caller's defaults.

    A malformed tag_rules entry (missing provider_prefix/tag/target) or
    weighted_groups member (missing model/weight, or a non-integer weight)
    is skipped with a warning.
    """
    section = _config.get("router_settings")
    if not section:
        return None
    tag_rules: dict[tuple[str, str], str] = {}
    for r in section.get("tag_rules", []):
        provider_prefix = r.get("provider_prefix") if isinstance(r, dict) \
            else None
        tag = r.get("tag") if isinstance(r, dict) else None
        target = r.get("target") if isinstance(r, dict) else None
        if not provider_prefix or not tag or not target:
            logging.warning(
                "Skipping malformed tag_rules entry (needs "
                "provider_prefix/tag/target): %r", r)
            continue
        tag_rules[(provider_prefix, tag)] = target

    weighted: dict[str, list[tuple[str, int]]] = {}
    for group, members in section.get("weighted_groups", {}).items():
        parsed: list[tuple[str, int]] = []
        for m in members:
            model = m.get("model") if isinstance(m, dict) else None
            weight = m.get("weight") if isinstance(m, dict) else None
            try:
                weight_int = int(weight)
            except (TypeError, ValueError):
                logging.warning(
                    "Skipping malformed weighted_groups member in %r "
                    "(non-integer weight): %r", group, m)
                continue
            if not model:
                logging.warning(
                    "Skipping malformed weighted_groups member in %r "
                    "(missing model): %r", group, m)
                continue
            parsed.append((model, weight_int))
        weighted[group] = parsed
    return RoutingSettings(
        model_group_alias=dict(section.get("model_group_alias", {})),
        tag_rules=tag_rules,
        weighted_groups=weighted,
        shuffle_groups={
            k: list(v)
            for k, v in section.get("shuffle_groups", {}).items()
        },
    )


def telemetry_settings() -> TelemetrySettings:
    section = _config.get("litellm_settings") or {}
    return TelemetrySettings(
        redact_user_api_key_info=bool(
            section.get("redact_user_api_key_info", False)))


def quota_settings() -> QuotaSettings:
    section = _config.get("general_settings") or {}
    return QuotaSettings(fail_open=bool(section.get("quota_fail_open", True)))
