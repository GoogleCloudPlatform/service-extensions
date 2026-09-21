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

The YAML shape mirrors LiteLLM's /key/generate parameter names, with two
deliberate differences: budgets are in tokens, and durations are whole
seconds (`budget_duration: 2592000`), so a LiteLLM-style `"30d"` fails
loudly at seed time instead of being parsed.

Run from a machine with Redis access (for Memorystore, a VM or
Cloud Shell inside the VPC):

    python seed_keys.py --host 10.0.0.3 --file keys.yaml

The gateway has no key-management API by design; this seeder plus the file
is the sample's substitute for LiteLLM's /key/generate endpoint.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
from typing import Any

# The seeder is a batch job, not a request path: it runs once, writes a
# handful of keys and exits, so the synchronous client is the right
# one here even though quota.py uses redis.asyncio.
import redis
import yaml

# The seeder is the only writer of these hashes, so it is also where every
# field is validated and normalized into the form quota.py reads. Timestamps
# become timezone-aware UTC and lists become JSON arrays. Windows are given
# in seconds and stay in seconds, so no unit is ever parsed or converted.
# The request path then does no format sniffing and no error recovery: a bad
# value fails the seed run instead of being discovered while serving traffic.
_INT_FIELDS = ("token_budget", "rpm_limit", "tpm_limit", "soft_budget")
_DURATION_FIELDS = ("budget_duration",)
_TIMESTAMP_FIELDS = ("expires",)
_LIST_FIELDS = ("models",)
_BUDGET_FIELDS = ("model_max_budget",)
_SUPPORTED_FIELDS = (
    ("key",) + _INT_FIELDS + _DURATION_FIELDS + _TIMESTAMP_FIELDS
    + _LIST_FIELDS + _BUDGET_FIELDS)

_MODEL_BUDGET_FIELDS = ("budget_limit", "time_period")


def _key_hash(api_key: str) -> str:
    """SHA-256 of a virtual key, matching quota.key_hash().

    Virtual keys are credentials and are never used as Redis key names
    directly. This duplicates quota.key_hash() rather than importing it so
    the seeder still runs standalone (`python seed_keys.py ...`) from this
    directory, outside the package. The two must stay identical or the
    callout will not find seeded keys.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _int_field(value: Any, field: str) -> int:
    """Coerce a limit to a non-negative int.

    0 is kept as a real limit of zero rather than folded into "unset":
    quota.py treats an absent field as unlimited and an explicit 0 as
    denying everything, so the difference has to survive being written.
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field}: expected an integer, got {value!r}")
    try:
        number = int(value)
    except ValueError as e:
        raise ValueError(
            f"{field}: expected an integer, got {value!r}") from e
    if number < 0:
        raise ValueError(f"{field}: must not be negative, got {value!r}")
    return number


def _duration_seconds(value: Any, field: str) -> int:
    """Validate a window length given in whole seconds.

    Windows are seconds everywhere: in keys.yaml, in Redis, and in
    quota.py. There is deliberately no suffix syntax to parse, so there is
    no unit to get wrong and no parser to keep correct. Write the arithmetic
    in the file instead, where a reader can check it:

        budget_duration: 2592000    # 30 days
    """
    seconds = _int_field(value, field)
    if seconds <= 0:
        raise ValueError(
            f"{field}: window must be a positive number of seconds, got "
            f"{value!r}")
    return seconds


def _utc_timestamp(value: Any, field: str) -> str:
    """Normalize an expiry to a timezone-aware UTC ISO-8601 string.

    A timestamp written without an offset is read as UTC. Pinning the
    timezone here is what lets quota.py compare with a single
    fromisoformat() call instead of guessing.
    """
    try:
        parsed = datetime.datetime.fromisoformat(str(value).strip())
    except ValueError as e:
        raise ValueError(
            f"{field}: cannot parse timestamp {value!r}; expected "
            f"ISO-8601, e.g. 2026-12-31T23:59:59Z") from e
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc).isoformat()


def _models_list(value: Any, field: str) -> list[str]:
    """Normalize the model allowlist to a list of non-empty strings."""
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value if str(v).strip()]
    else:
        raise ValueError(
            f"{field}: expected a list of model ids, got {value!r}")
    if not items:
        # An empty allowlist would read as "no allowlist" and quietly permit
        # every model, which is the opposite of what writing it suggests.
        raise ValueError(
            f"{field}: must not be empty; omit the field to allow all "
            f"models")
    return items


def _model_budgets(value: Any, field: str) -> dict[str, dict[str, int]]:
    """Validate model_max_budget and resolve each time_period to seconds."""
    if not isinstance(value, dict):
        raise ValueError(
            f"{field}: expected a mapping of model id to budget, got "
            f"{value!r}")
    budgets: dict[str, dict[str, int]] = {}
    for model, budget in value.items():
        where = f"{field}.{model}"
        if not isinstance(budget, dict):
            raise ValueError(
                f"{where}: expected a mapping with budget_limit and "
                f"time_period, got {budget!r}")
        unknown = sorted(set(budget) - set(_MODEL_BUDGET_FIELDS))
        if unknown:
            raise ValueError(
                f"{where}: unsupported field(s) {', '.join(unknown)}; "
                f"supported: {', '.join(_MODEL_BUDGET_FIELDS)}")
        entry: dict[str, int] = {}
        if "budget_limit" in budget:
            entry["budget_limit"] = _int_field(
                budget["budget_limit"], f"{where}.budget_limit")
        if "time_period" in budget:
            entry["time_period"] = _duration_seconds(
                budget["time_period"], f"{where}.time_period")
        budgets[str(model)] = entry
    return budgets


def seed(
    client: Any,
    keys: list[dict[str, Any]],
    replace: bool = False,
) -> int:
    """Write each key definition as a `key:{sha256(vk)}` hash. Returns count.

    Virtual keys are credentials, so the SHA-256 of the key, never the key
    itself, is what names the Redis entry. Anyone reading the datastore
    sees only hashes.

    Every entry always creates the hash, even one with no limit fields, so
    a key with no limits is still known to quota.check() and tracked rather
    than treated as unknown and blocked.

    Every field is validated and normalized here. An unrecognized field is
    an error rather than a silent no-op: a key written with `rpm_limits`
    instead of `rpm_limit` would otherwise seed as an unlimited key and
    report success.

    Raises:
        ValueError: if an entry is missing the `key` field, names a field
            that is not supported, or carries a value that cannot be
            normalized.
    """
    for entry in keys:
        vk = entry.get("key")
        if not vk:
            raise ValueError(f"key entry missing 'key' field: {entry}")
        mapping: dict[str, str] = {}
        for name, value in entry.items():
            if name == "key":
                continue
            if name in _INT_FIELDS:
                mapping[name] = str(_int_field(value, name))
            elif name in _DURATION_FIELDS:
                mapping[name] = str(_duration_seconds(value, name))
            elif name in _TIMESTAMP_FIELDS:
                mapping[name] = _utc_timestamp(value, name)
            elif name in _LIST_FIELDS:
                mapping[name] = json.dumps(_models_list(value, name))
            elif name in _BUDGET_FIELDS:
                mapping[name] = json.dumps(_model_budgets(value, name))
            else:
                raise ValueError(
                    f"key {vk!r}: unsupported field {name!r}; supported: "
                    f"{', '.join(_SUPPORTED_FIELDS)}")
        kh = _key_hash(vk)
        # The hash doubles as the "this key exists" marker, so a key with no
        # limits is still known to quota.check() rather than treated as
        # unknown and blocked.
        mapping["key_hash"] = kh
        # Replace is delete + write: run both in one transaction so a request
        # arriving mid-update never sees a missing key and gets a spurious
        # 401.
        pipe = client.pipeline(transaction=True)
        if replace:
            pipe.delete(f"key:{kh}")
        pipe.hset(f"key:{kh}", mapping=mapping)
        pipe.execute()
        logging.info("Seeded key %s (%d fields)", kh[:16], len(mapping))
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
    # Same two env vars the callout reads, so the seeder reaches an
    # authenticated, in-transit-encrypted Memorystore instance without a
    # second way to configure it. Both are unset for an instance with auth
    # disabled, and the connection is then plain.
    client = redis.Redis(
        host=args.host, port=args.port, decode_responses=True,
        password=os.getenv("REDIS_AUTH_STRING") or None,
        ssl=os.getenv("REDIS_TLS", "").lower() == "true",
        ssl_cert_reqs=None)
    count = seed(client, doc.get("keys", []), replace=args.replace)
    logging.info("Done: %d keys seeded.", count)


if __name__ == "__main__":
    main()
