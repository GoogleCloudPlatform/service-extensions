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

"""Unit tests for the virtual-key seeder."""

import json

import fakeredis
import pytest

from extproc.example.litellm_gateway import seed_keys


def _kh(vk):
    """Redis key name for a virtual key (never the key itself)."""
    return f"key:{seed_keys._key_hash(vk)}"


@pytest.fixture
def client():
    return fakeredis.FakeRedis(decode_responses=True)


def test_seed_writes_all_fields(client):
    count = seed_keys.seed(client, [{
        "key": "vk-demo",
        "token_budget": 100000,
        "budget_duration": 30 * 86400,
        "rpm_limit": 60,
        "tpm_limit": 50000,
        "soft_budget": 80000,
        "expires": "2027-01-01T00:00:00+00:00",
        "models": ["vertex_ai/*", "anthropic/claude-haiku-4-5"],
        "model_max_budget": {
            "anthropic/claude-haiku-4-5": {
                "budget_limit": 5000, "time_period": 86400}},
    }])
    assert count == 1
    cfg = client.hgetall(_kh("vk-demo"))
    assert cfg["token_budget"] == "100000"
    # Durations are resolved to whole seconds on the way in, so the request
    # path never parses a unit suffix.
    assert cfg["budget_duration"] == str(30 * 86400)
    assert cfg["expires"] == "2027-01-01T00:00:00+00:00"
    assert json.loads(cfg["models"]) == [
        "vertex_ai/*", "anthropic/claude-haiku-4-5"]
    budget = json.loads(cfg["model_max_budget"])[
        "anthropic/claude-haiku-4-5"]
    assert budget["budget_limit"] == 5000
    assert budget["time_period"] == 86400


def test_seed_requires_key_field(client):
    with pytest.raises(ValueError):
        seed_keys.seed(client, [{"token_budget": 1}])


def test_seed_replace_clears_stale_fields(client):
    client.hset(_kh("vk1"), mapping={"rpm_limit": 5, "stale_field": "x"})
    seed_keys.seed(client, [{"key": "vk1", "rpm_limit": 10}], replace=True)
    cfg = client.hgetall(_kh("vk1"))
    assert cfg == {"key_hash": seed_keys._key_hash("vk1"),
                   "rpm_limit": "10"}


def test_seed_without_replace_merges(client):
    client.hset(_kh("vk1"), mapping={"token_budget": 500})
    seed_keys.seed(client, [{"key": "vk1", "rpm_limit": 10}])
    cfg = client.hgetall(_kh("vk1"))
    assert cfg["token_budget"] == "500"
    assert cfg["rpm_limit"] == "10"


def test_seed_key_with_no_limits_creates_hash(client):
    seed_keys.seed(client, [{"key": "vk-unlimited"}])
    assert client.hgetall(_kh("vk-unlimited")) == {
        "key_hash": seed_keys._key_hash("vk-unlimited")}

def test_unknown_field_is_rejected(client):
    with pytest.raises(ValueError, match="rpm_limits"):
        seed_keys.seed(client, [{"key": "vk1", "rpm_limits": 10}])
    assert client.hgetall(_kh("vk1")) == {}


def test_bad_duration_is_rejected(client):
    # There is no suffix syntax: a window is a number of seconds.
    with pytest.raises(ValueError, match="budget_duration"):
        seed_keys.seed(client, [{"key": "vk1", "budget_duration": "30d"}])


def test_zero_duration_is_rejected(client):
    # A zero-length window would make every request its own bucket.
    with pytest.raises(ValueError, match="positive"):
        seed_keys.seed(client, [{"key": "vk1", "budget_duration": 0}])


def test_negative_limit_is_rejected(client):
    with pytest.raises(ValueError, match="negative"):
        seed_keys.seed(client, [{"key": "vk1", "rpm_limit": -1}])


def test_non_numeric_limit_is_rejected(client):
    with pytest.raises(ValueError, match="rpm_limit"):
        seed_keys.seed(client, [{"key": "vk1", "rpm_limit": "lots"}])


def test_zero_limit_is_preserved(client):
    # 0 has to survive the write: quota.py reads an absent field as
    # unlimited and an explicit 0 as denying everything.
    seed_keys.seed(client, [{"key": "vk1", "rpm_limit": 0}])
    assert client.hget(_kh("vk1"), "rpm_limit") == "0"


def test_window_is_stored_as_given_seconds(client):
    # Seconds in, seconds out. Nothing converts, so nothing can convert
    # wrongly.
    seed_keys.seed(client, [
        {"key": "week", "budget_duration": 7 * 86400},
        {"key": "raw", "budget_duration": 900},
        {"key": "text", "budget_duration": "900"},
    ])
    assert client.hget(_kh("week"), "budget_duration") == "604800"
    assert client.hget(_kh("raw"), "budget_duration") == "900"
    assert client.hget(_kh("text"), "budget_duration") == "900"


def test_naive_expiry_is_stored_as_utc(client):
    seed_keys.seed(client, [{"key": "vk1", "expires": "2027-01-01T00:00:00"}])
    assert client.hget(_kh("vk1"), "expires") == "2027-01-01T00:00:00+00:00"


def test_offset_expiry_is_converted_to_utc(client):
    seed_keys.seed(
        client, [{"key": "vk1", "expires": "2027-01-01T05:00:00+05:00"}])
    assert client.hget(_kh("vk1"), "expires") == "2027-01-01T00:00:00+00:00"


def test_bad_expiry_is_rejected(client):
    with pytest.raises(ValueError, match="expires"):
        seed_keys.seed(client, [{"key": "vk1", "expires": "soon"}])


def test_comma_separated_models_become_a_json_array(client):
    seed_keys.seed(client, [{"key": "vk1", "models": "a/b, c/*"}])
    assert json.loads(client.hget(_kh("vk1"), "models")) == ["a/b", "c/*"]


def test_empty_models_list_is_rejected(client):
    # An empty allowlist reads as "no allowlist" downstream, which permits
    # every model. Writing it almost certainly meant the opposite.
    with pytest.raises(ValueError, match="must not be empty"):
        seed_keys.seed(client, [{"key": "vk1", "models": []}])


def test_model_budget_period_is_seconds(client):
    seed_keys.seed(client, [{"key": "vk1", "model_max_budget": {
        "m": {"budget_limit": 10, "time_period": 86400}}}])
    budget = json.loads(client.hget(_kh("vk1"), "model_max_budget"))["m"]
    assert budget == {"budget_limit": 10, "time_period": 86400}


def test_model_budget_must_be_a_mapping_of_mappings(client):
    with pytest.raises(ValueError, match="model_max_budget"):
        seed_keys.seed(client, [{"key": "vk1", "model_max_budget": {"m": 5}}])


def test_model_budget_unknown_field_is_rejected(client):
    with pytest.raises(ValueError, match="budget_limits"):
        seed_keys.seed(client, [{"key": "vk1", "model_max_budget": {
            "m": {"budget_limits": 10}}}])
