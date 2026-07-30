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


@pytest.fixture(autouse=True)
def reset_config():
    gateway_config._reset()
    yield
    gateway_config._reset()


def test_defaults_without_config():
    assert gateway_config.routing_settings() is None
    assert gateway_config.telemetry_settings().redact_user_api_key_info is False
    assert gateway_config.quota_settings().fail_open is True


def test_full_config_dict():
    gateway_config._load_dict({
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
        "litellm_settings": {"redact_user_api_key_info": True},
        "general_settings": {"quota_fail_open": False},
    })
    rs = gateway_config.routing_settings()
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
    assert gateway_config.telemetry_settings().redact_user_api_key_info is True
    assert gateway_config.quota_settings().fail_open is False


def test_partial_config_keeps_other_defaults():
    gateway_config._load_dict({
        "litellm_settings": {"redact_user_api_key_info": True}})
    assert gateway_config.routing_settings() is None
    assert gateway_config.telemetry_settings().redact_user_api_key_info is True
    assert gateway_config.quota_settings().fail_open is True


def test_load_from_yaml_file(tmp_path, monkeypatch):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "general_settings:\n  quota_fail_open: false\n", encoding="utf-8")
    monkeypatch.setenv("GATEWAY_CONFIG", str(cfg))
    gateway_config.load()
    assert gateway_config.quota_settings().fail_open is False


def test_load_without_env_is_noop(monkeypatch):
    monkeypatch.delenv("GATEWAY_CONFIG", raising=False)
    gateway_config.load()
    assert gateway_config.routing_settings() is None


def test_malformed_yaml_leaves_routing_disabled(tmp_path, monkeypatch, caplog):
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("router_settings: [unclosed", encoding="utf-8")
    monkeypatch.setenv("GATEWAY_CONFIG", str(cfg))
    with caplog.at_level("WARNING"):
        gateway_config.load()  # must not raise
    assert gateway_config.routing_settings() is None
    assert gateway_config.quota_settings().fail_open is True
    assert any(str(cfg) in r.message for r in caplog.records)


def test_tag_rules_entry_missing_target_is_skipped(caplog):
    gateway_config._load_dict({
        "router_settings": {
            "tag_rules": [
                {"provider_prefix": "vertex_ai/", "tag": "premium"},
                {"provider_prefix": "anthropic/", "tag": "premium",
                 "target": "anthropic/claude-opus"},
            ],
        },
    })
    with caplog.at_level("WARNING"):
        rs = gateway_config.routing_settings()
    assert rs.tag_rules == {
        ("anthropic/", "premium"): "anthropic/claude-opus"}
    assert any("tag_rules" in r.message for r in caplog.records)
