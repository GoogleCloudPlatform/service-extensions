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

"""Unit tests for the gateway_config module."""

import pytest

from extproc.example.litellm_gateway import gateway_config


def test_defaults_without_config():
    cfg = gateway_config.GatewayConfig()
    assert cfg.routing is None
    assert cfg.telemetry.redact_user_api_key_info is True
    assert cfg.quota.fail_open is False
    assert cfg.quota.allow_unauthenticated is False


def test_full_config_dict():
    cfg = gateway_config.GatewayConfig.from_dict({
        "router_settings": {
            "model_group_alias": {"fast": "vertex_ai/gemini-2.5-flash"},
            "tag_rules": [
                {"provider_prefix": "vertex_ai/", "tag": "premium",
                 "target": "vertex_ai/gemini-2.5-pro"},
            ],
            "weighted_groups": {
                "vertex_ai/gemini-2.5-flash": [
                    {"model": "vertex_ai/gemini-2.5-flash", "weight": 70},
                    {"model": "vertex_ai/gemini-2.5-pro", "weight": 30},
                ],
            },
            "shuffle_groups": {
                "vertex-shuffle": ["vertex_ai/gemini-2.5-flash"],
            },
        },
        "litellm_settings": {"redact_user_api_key_info": False},
        "general_settings": {"quota_fail_open": False},
    })
    rs = cfg.routing
    assert rs.model_group_alias == {"fast": "vertex_ai/gemini-2.5-flash"}
    assert rs.tag_rules == {
        ("vertex_ai/", "premium"): "vertex_ai/gemini-2.5-pro"}
    assert rs.weighted_groups == {
        "vertex_ai/gemini-2.5-flash": [
            ("vertex_ai/gemini-2.5-flash", 70),
            ("vertex_ai/gemini-2.5-pro", 30),
        ]}
    assert rs.shuffle_groups == {
        "vertex-shuffle": ["vertex_ai/gemini-2.5-flash"]}
    assert cfg.telemetry.redact_user_api_key_info is False
    assert cfg.quota.fail_open is False


def test_partial_config_keeps_other_defaults():
    cfg = gateway_config.GatewayConfig.from_dict({
        "litellm_settings": {"redact_user_api_key_info": False}})
    assert cfg.routing is None
    assert cfg.telemetry.redact_user_api_key_info is False
    assert cfg.quota.fail_open is False
    assert cfg.quota.allow_unauthenticated is False


def test_load_from_yaml_file(tmp_path, monkeypatch):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "general_settings:\n  quota_fail_open: false\n", encoding="utf-8")
    monkeypatch.setenv("GATEWAY_CONFIG", str(cfg))
    assert gateway_config.GatewayConfig.load().quota.fail_open is False


def test_load_without_env_gives_defaults(monkeypatch):
    monkeypatch.delenv("GATEWAY_CONFIG", raising=False)
    assert (gateway_config.GatewayConfig.load()
            == gateway_config.GatewayConfig())


def test_malformed_yaml_is_fatal(tmp_path, monkeypatch, caplog):
    # A config file that was explicitly named but cannot be parsed must stop
    # startup: serving with silently different behavior is worse than not
    # starting at all.
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("router_settings: [unclosed", encoding="utf-8")
    monkeypatch.setenv("GATEWAY_CONFIG", str(cfg))
    with caplog.at_level("ERROR"):
        with pytest.raises(Exception):
            gateway_config.GatewayConfig.load()
    assert any(str(cfg) in r.message for r in caplog.records)


def test_missing_config_file_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_CONFIG", str(tmp_path / "does-not-exist.yaml"))
    with pytest.raises(Exception):
        gateway_config.GatewayConfig.load()

def test_explicit_null_keeps_the_default_on_boolean_settings():
    # A YAML line written as `redact_user_api_key_info:` with no value
    # parses to None. That must mean "use the default", not False, or the
    # typo silently switches redaction off, the unsafe direction.
    import textwrap

    import yaml
    cfg = gateway_config.GatewayConfig.from_dict(yaml.safe_load(
        textwrap.dedent("""\
            litellm_settings:
              redact_user_api_key_info:
            general_settings:
              quota_fail_open:
              quota_allow_unauthenticated:
        """)))
    assert cfg.telemetry.redact_user_api_key_info is True
    assert cfg.quota.fail_open is False
    assert cfg.quota.allow_unauthenticated is False


def test_tag_rules_entry_missing_target_is_fatal():
    with pytest.raises(ValueError, match="missing target"):
        gateway_config.GatewayConfig.from_dict({
            "router_settings": {
                "tag_rules": [
                    {"provider_prefix": "vertex_ai/", "tag": "premium"},
                ],
            },
        })


def test_tag_rules_entry_must_be_a_mapping():
    with pytest.raises(ValueError, match="tag_rules"):
        gateway_config.GatewayConfig.from_dict(
            {"router_settings": {"tag_rules": ["vertex_ai/"]}})


def test_weighted_member_missing_model_is_fatal():
    with pytest.raises(ValueError, match="missing model"):
        gateway_config.GatewayConfig.from_dict({
            "router_settings": {
                "weighted_groups": {"g": [{"weight": 50}]}}})


def test_weighted_member_non_integer_weight_is_fatal():
    with pytest.raises(ValueError, match="integer weight"):
        gateway_config.GatewayConfig.from_dict({
            "router_settings": {
                "weighted_groups": {"g": [{"model": "m", "weight": "many"}]}}})


def test_weighted_member_negative_weight_is_fatal():
    # A negative weight corrupts the bucket arithmetic rather than removing
    # the member from the split.
    with pytest.raises(ValueError, match="negative weight"):
        gateway_config.GatewayConfig.from_dict({
            "router_settings": {
                "weighted_groups": {"g": [{"model": "m", "weight": -1}]}}})


def test_weighted_member_must_be_a_mapping():
    with pytest.raises(ValueError, match="weighted_groups"):
        gateway_config.GatewayConfig.from_dict({
            "router_settings": {"weighted_groups": {"g": ["m"]}}})


def test_section_must_be_a_mapping():
    with pytest.raises(ValueError, match="router_settings"):
        gateway_config.GatewayConfig.from_dict(
            {"router_settings": ["not", "a", "mapping"]})


def test_a_rejected_config_cannot_disturb_an_existing_one():
    # from_dict returns a new value and mutates nothing, so a config that
    # fails to parse cannot half-replace one already in use. This used to
    # depend on the order of assignments inside the module.
    good = gateway_config.GatewayConfig.from_dict({
        "general_settings": {"quota_allow_unauthenticated": True}})
    with pytest.raises(ValueError):
        gateway_config.GatewayConfig.from_dict({
            "general_settings": {"quota_fail_open": True},
            "router_settings": {"tag_rules": [{"tag": "premium"}]},
        })
    assert good.quota.allow_unauthenticated is True
    assert good.quota.fail_open is False
