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

"""Seed virtual keys into Redis from a keys.yaml file.

The YAML shape mirrors LiteLLM's /key/generate parameters (with token units
for budgets). Run from a machine with Redis access (for Memorystore, a VM or
Cloud Shell inside the VPC):

    python seed_keys.py --host 10.0.0.3 --file keys.yaml

The gateway has no key-management API by design; this seeder plus the file
is the sample's substitute for LiteLLM's /key/generate endpoint.
"""

import argparse
import hashlib
import json
import logging
from typing import Any

import redis
import yaml

# Fields stored verbatim (stringified); JSON fields handled separately.
_SCALAR_FIELDS = (
    "token_budget", "budget_duration", "rpm_limit", "tpm_limit",
    "soft_budget", "expires",
)
_JSON_FIELDS = ("models", "model_max_budget")


def seed(
    client: Any,
    keys: list[dict[str, Any]],
    replace: bool = False,
) -> int:
    """Write each key definition as a `key:{vk}` hash. Returns count.

    Every entry always creates the hash, even one with no fields besides
    `key`. The `key` field itself is always written (self-descriptive,
    mirrors LiteLLM's key-info object; quota.py ignores unknown fields),
    so a key with no limits is still known to quota.check() and is
    tracked rather than treated as an unknown, blocked key.

    Raises:
        ValueError: if an entry is missing the `key` field.
    """
    for entry in keys:
        vk = entry.get("key")
        if not vk:
            raise ValueError(f"key entry missing 'key' field: {entry}")
        mapping: dict[str, str] = {"key": vk}
        for name in _SCALAR_FIELDS:
            if name in entry:
                mapping[name] = str(entry[name])
        for name in _JSON_FIELDS:
            if name in entry:
                mapping[name] = json.dumps(entry[name])
        if replace:
            client.delete(f"key:{vk}")
        client.hset(f"key:{vk}", mapping=mapping)
        key_hash = hashlib.sha256(vk.encode("utf-8")).hexdigest()[:16]
        logging.info("Seeded key %s (%d fields)", key_hash, len(mapping))
    return len(keys)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed litellm-gateway virtual keys into Redis.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--file", default="keys.yaml")
    parser.add_argument(
        "--replace", action="store_true",
        help="Delete each key hash before writing (drops stale fields).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with open(args.file, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    client = redis.Redis(
        host=args.host, port=args.port, decode_responses=True)
    count = seed(client, doc.get("keys", []), replace=args.replace)
    logging.info("Done: %d keys seeded.", count)


if __name__ == "__main__":
    main()
