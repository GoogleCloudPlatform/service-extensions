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


@pytest.fixture
def client():
    return fakeredis.FakeRedis(decode_responses=True)


def test_seed_writes_all_fields(client):
    count = seed_keys.seed(client, [{
        "key": "vk-demo",
        "token_budget": 100000,
        "budget_duration": "30d",
        "rpm_limit": 60,
        "tpm_limit": 50000,
        "soft_budget": 80000,
        "expires": "2027-01-01T00:00:00+00:00",
        "models": ["vertex_ai/*", "anthropic/claude-haiku-4-5"],
        "model_max_budget": {
            "anthropic/claude-haiku-4-5": {
                "budget_limit": 5000, "time_period": "1d"}},
    }])
    assert count == 1
    cfg = client.hgetall("key:vk-demo")
    assert cfg["token_budget"] == "100000"
    assert cfg["budget_duration"] == "30d"
    assert json.loads(cfg["models"]) == [
        "vertex_ai/*", "anthropic/claude-haiku-4-5"]
    assert json.loads(cfg["model_max_budget"])[
        "anthropic/claude-haiku-4-5"]["budget_limit"] == 5000


def test_seed_requires_key_field(client):
    with pytest.raises(ValueError):
        seed_keys.seed(client, [{"token_budget": 1}])


def test_seed_replace_clears_stale_fields(client):
    client.hset("key:vk1", mapping={"rpm_limit": 5, "stale_field": "x"})
    seed_keys.seed(client, [{"key": "vk1", "rpm_limit": 10}], replace=True)
    cfg = client.hgetall("key:vk1")
    assert cfg == {"key": "vk1", "rpm_limit": "10"}


def test_seed_without_replace_merges(client):
    client.hset("key:vk1", mapping={"token_budget": 500})
    seed_keys.seed(client, [{"key": "vk1", "rpm_limit": 10}])
    cfg = client.hgetall("key:vk1")
    assert cfg["token_budget"] == "500"
    assert cfg["rpm_limit"] == "10"


def test_seed_key_with_no_limits_creates_hash(client):
    seed_keys.seed(client, [{"key": "vk-unlimited"}])
    assert client.hgetall("key:vk-unlimited") == {"key": "vk-unlimited"}
