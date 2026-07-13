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

"""Loads and hot-reloads the Prompt-Amender YAML ruleset from one of three
configurable backends:

  - env:  static, read once from CONFIG_VALUE at startup. No reload support.
  - gcs:  polls a `gs://bucket/rules.yaml` object, using the object
          generation number to detect changes.
  - git:  polls a remote repo with `git ls-remote` to check the HEAD SHA of
          the configured branch, and does a shallow clone when it changes.

A background thread performs the poll and executes an ATOMIC swap of the
active ruleset (single reference reassignment, safe to read concurrently
from request-handling threads without a lock). If a newly loaded
configuration fails syntax or semantic validation, the update is rejected
and the service continues serving the last-known-good configuration.
"""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import yaml

from rule_engine import Ruleset, parse_ruleset, RulesetValidationError


class ConfigSource:
    def fetch(self) -> tuple:
        """Returns (raw_yaml_text, version_token)."""
        raise NotImplementedError

    def supports_polling(self) -> bool:
        return True


class EnvConfigSource(ConfigSource):
    def __init__(self, config_value: str):
        self._value = config_value

    def fetch(self):
        return self._value, "static"

    def supports_polling(self) -> bool:
        return False


class GcsConfigSource(ConfigSource):
    def __init__(self, gcs_uri: str):
        from google.cloud import storage  # lazy import

        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"GCS_RULES_URI must start with gs://, got: {gcs_uri}")
        bucket_name, _, blob_name = gcs_uri[len("gs://"):].partition("/")
        self._client = storage.Client()
        self._bucket_name = bucket_name
        self._blob_name = blob_name

    def fetch(self):
        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_name)
        blob.reload()
        version_token = str(blob.generation)
        raw = blob.download_as_text()
        return raw, version_token


class GitConfigSource(ConfigSource):
    def __init__(self, repo_url: str, branch: str, rules_path: str):
        self._repo_url = repo_url
        self._branch = branch
        self._rules_path = rules_path

    def _current_remote_sha(self) -> str:
        import subprocess

        out = subprocess.run(
            ["git", "ls-remote", self._repo_url, f"refs/heads/{self._branch}"],
            capture_output=True, text=True, check=True, timeout=15,
        )
        if not out.stdout.strip():
            raise RuntimeError(f"branch {self._branch} not found in {self._repo_url}")
        return out.stdout.split()[0]

    def fetch(self):
        import subprocess
        import tempfile
        import os

        sha = self._current_remote_sha()
        clone_dir = tempfile.mkdtemp(prefix="prompt-amender-rules-")
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", self._branch, self._repo_url, clone_dir],
            check=True, capture_output=True, timeout=60,
        )
        rules_file = os.path.join(clone_dir, self._rules_path)
        with open(rules_file, "r", encoding="utf-8") as f:
            raw = f.read()
        return raw, sha


def build_config_source(
    source: str,
    config_value: str = "",
    gcs_rules_uri: str = "",
    git_repo_url: str = "",
    git_branch: str = "main",
    git_rules_path: str = "rules.yaml",
) -> ConfigSource:
    if source == "env":
        if not config_value:
            raise RuntimeError("CONFIG_SOURCE=env requires CONFIG_VALUE to be set")
        return EnvConfigSource(config_value)
    if source == "gcs":
        if not gcs_rules_uri:
            raise RuntimeError("CONFIG_SOURCE=gcs requires GCS_RULES_URI to be set")
        return GcsConfigSource(gcs_rules_uri)
    if source == "git":
        if not git_repo_url:
            raise RuntimeError("CONFIG_SOURCE=git requires GIT_REPO_URL to be set")
        return GitConfigSource(git_repo_url, git_branch, git_rules_path)
    raise RuntimeError(f"Unknown CONFIG_SOURCE: {source}")


@dataclass
class ReloadMetrics:
    success_count: int = 0
    failure_count: int = 0
    last_reload_at: float = 0.0
    last_version_token: str = ""


class HotReloadingRuleProvider:
    """Holds the currently-active Ruleset and refreshes it from a
    ConfigSource on a background thread. `current()` is safe to call from
    any number of concurrent gRPC handler threads without locking."""

    def __init__(
        self,
        source: ConfigSource,
        poll_interval_seconds: int,
        logger: logging.Logger,
        on_reload: Optional[Callable[[bool], None]] = None,
    ):
        self._source = source
        self._poll_interval_seconds = poll_interval_seconds
        self._logger = logger
        self._on_reload = on_reload
        self._ruleset = Ruleset(rules=[])
        self._last_version_token = None
        self.metrics = ReloadMetrics()
        self._stop_event = threading.Event()
        self._thread = None

    def current(self) -> Ruleset:
        return self._ruleset

    def load_initial(self) -> None:
        self._reload_once(force=True)

    def start_background_polling(self) -> None:
        if not self._source.supports_polling():
            return
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self._poll_interval_seconds)
            self._reload_once(force=False)

    def _reload_once(self, force: bool) -> None:
        try:
            raw_yaml, version_token = self._source.fetch()
        except Exception:
            self._logger.exception("failed to fetch prompt-amender rules from config source")
            self.metrics.failure_count += 1
            if self._on_reload:
                self._on_reload(False)
            return

        if not force and version_token == self._last_version_token:
            return

        try:
            parsed = yaml.safe_load(raw_yaml)
            new_ruleset = parse_ruleset(parsed)
        except (yaml.YAMLError, RulesetValidationError) as exc:
            self._logger.error(
                "rejected invalid prompt-amender configuration; keeping last-known-good ruleset",
                extra={"version_token": version_token, "error": str(exc)},
            )
            self.metrics.failure_count += 1
            if self._on_reload:
                self._on_reload(False)
            return

        self._ruleset = new_ruleset  # atomic swap
        self._last_version_token = version_token
        self.metrics.success_count += 1
        self.metrics.last_reload_at = time.time()
        self.metrics.last_version_token = version_token
        self._logger.info(
            "prompt_amender_config_reloads_total",
            extra={"status": "success", "version_token": version_token, "rule_count": len(new_ruleset.rules)},
        )
        if self._on_reload:
            self._on_reload(True)
