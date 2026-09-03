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

  router_settings:    routing-strategy config, used to build a
                      routing.Router (model_group_alias matches LiteLLM's
                      key of the same name; the other three configure this
                      sample's strategies).
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
    allow_unauthenticated: bool


# Defaults, both the safe choice.
#
# fail_open is False: if the quota backend is unreachable, LLM calls are
# expensive enough that rejecting beats serving unmetered traffic.
# allow_unauthenticated is False so a caller cannot evade its budget by
# dropping the Authorization header. Redaction is on because the hashed
# virtual key is still an identifier.
_DEFAULT_TELEMETRY = TelemetrySettings(redact_user_api_key_info=True)
_DEFAULT_QUOTA = QuotaSettings(fail_open=False, allow_unauthenticated=False)


class GatewayConfig(NamedTuple):

    routing: Optional[RoutingSettings] = None
    telemetry: TelemetrySettings = _DEFAULT_TELEMETRY
    quota: QuotaSettings = _DEFAULT_QUOTA

    @classmethod
    def load(cls) -> "GatewayConfig":
        """Config from the YAML named by GATEWAY_CONFIG, else the defaults.

        Raises if the file is named but cannot be read, parsed, or
        understood. A deployment that names a config file and then serves
        traffic with different behavior because that file was unreadable or
        malformed is worse than one that refuses to start, so this is
        deliberately fatal: the caller lets it propagate and the process
        exits.
        """
        path = os.getenv("GATEWAY_CONFIG", "")
        if not path:
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as e:
            logging.error("Failed to read GATEWAY_CONFIG %s: %s", path, e)
            raise
        try:
            config = cls.from_dict(raw)
        except Exception as e:
            logging.error("Invalid GATEWAY_CONFIG %s: %s", path, e)
            raise
        logging.info("Gateway config loaded from %s", path)
        return config

    @classmethod
    def from_dict(cls, cfg: dict[str, Any]) -> "GatewayConfig":
        """Parse an already-decoded config mapping.

        Everything is parsed here rather than on each read, so a malformed
        config is rejected.
        """
        cfg = cfg or {}
        if not isinstance(cfg, dict):
            raise ValueError(f"config: expected a mapping, got {cfg!r}")
        return cls(
            routing=_parse_routing(cfg.get("router_settings")),
            telemetry=_parse_telemetry(cfg.get("litellm_settings")),
            quota=_parse_quota(cfg.get("general_settings")),
        )


def _section(value: Any, name: str) -> dict[str, Any]:
    """Return a config section as a mapping, empty when absent."""
    if not value:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name}: expected a mapping, got {value!r}")
    return value


def _parse_tag_rules(section: dict[str, Any]) -> dict[tuple[str, str], str]:
    """tag_rules as a (provider_prefix, tag) -> target lookup."""
    rules: dict[tuple[str, str], str] = {}
    entries = section.get("tag_rules") or []
    if not isinstance(entries, list):
        raise ValueError(
            f"router_settings.tag_rules: expected a list, got {entries!r}")
    for entry in entries:
        where = "router_settings.tag_rules"
        if not isinstance(entry, dict):
            raise ValueError(
                f"{where}: expected a mapping with provider_prefix, tag and "
                f"target, got {entry!r}")
        missing = [
            f for f in ("provider_prefix", "tag", "target")
            if not entry.get(f)]
        if missing:
            raise ValueError(
                f"{where}: entry {entry!r} is missing {', '.join(missing)}")
        rules[(entry["provider_prefix"], entry["tag"])] = entry["target"]
    return rules


def _parse_weighted(
    section: dict[str, Any],
) -> dict[str, list[tuple[str, int]]]:
    """weighted_groups as a group -> [(model, weight)] lookup."""
    groups = _section(
        section.get("weighted_groups"), "router_settings.weighted_groups")
    weighted: dict[str, list[tuple[str, int]]] = {}
    for group, members in groups.items():
        where = f"router_settings.weighted_groups.{group}"
        if members is None:
            members = []
        if not isinstance(members, list):
            raise ValueError(f"{where}: expected a list, got {members!r}")
        parsed: list[tuple[str, int]] = []
        for member in members:
            if not isinstance(member, dict):
                raise ValueError(
                    f"{where}: expected a mapping with model and weight, "
                    f"got {member!r}")
            if not member.get("model"):
                raise ValueError(
                    f"{where}: entry {member!r} is missing model")
            try:
                weight = int(member["weight"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(
                    f"{where}: entry {member!r} needs an integer weight")
            if weight < 0:
                # A negative weight corrupts the bucket arithmetic rather
                # than removing the member. Drop the member instead.
                raise ValueError(
                    f"{where}: entry {member!r} has a negative weight")
            parsed.append((member["model"], weight))
        weighted[group] = parsed
    return weighted


def _parse_routing(value: Any) -> Optional[RoutingSettings]:
    """Parsed router_settings, or None to keep the caller's defaults."""
    if not value:
        return None
    section = _section(value, "router_settings")
    shuffle = _section(
        section.get("shuffle_groups"), "router_settings.shuffle_groups")
    for group, members in shuffle.items():
        if not isinstance(members, list):
            raise ValueError(
                f"router_settings.shuffle_groups.{group}: expected a list, "
                f"got {members!r}")
    return RoutingSettings(
        model_group_alias=dict(
            _section(section.get("model_group_alias"),
                     "router_settings.model_group_alias")),
        tag_rules=_parse_tag_rules(section),
        weighted_groups=_parse_weighted(section),
        shuffle_groups={k: list(v) for k, v in shuffle.items()},
    )


def _bool(section: dict[str, Any], key: str, default: bool) -> bool:
    """A boolean setting where absent and explicit null both mean default.

    `section.get(key, default)` is not enough: a YAML line written as
    `redact_user_api_key_info:` with no value parses to None, the key IS
    present, and `bool(None)` is False.
    """
    value = section.get(key)
    return default if value is None else bool(value)


def _parse_telemetry(value: Any) -> TelemetrySettings:
    """Parsed litellm_settings telemetry knobs."""
    section = _section(value, "litellm_settings")
    return TelemetrySettings(
        redact_user_api_key_info=_bool(
            section, "redact_user_api_key_info", True))


def _parse_quota(value: Any) -> QuotaSettings:
    """Parsed general_settings quota knobs."""
    section = _section(value, "general_settings")
    return QuotaSettings(
        fail_open=_bool(section, "quota_fail_open", False),
        allow_unauthenticated=_bool(
            section, "quota_allow_unauthenticated", False))
