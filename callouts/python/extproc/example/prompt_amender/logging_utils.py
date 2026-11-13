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

"""Structured JSON logging.

CUJ 4 requires `rule_id`, `op`, `caller_spiffe_id`, `original_len`,
`new_len`, and `latency_ms` as queryable fields, and requires that raw
prompt text never appear in logs. A plain `%`-formatted log line makes the
first requirement unqueryable and, on failure paths, risks the second if a
call site interpolates exception text that happens to echo template
content. This formatter renders `extra={"fields": {...}}` as top-level JSON
keys; call sites pass structured fields instead of building message
strings.
"""
import json
import logging


class JsonFormatter(logging.Formatter):
  """Renders each LogRecord as a single JSON object.

  Fields passed via `extra={"fields": {...}}` are merged in at the top
  level so they're directly queryable in Cloud Logging.
  """

  def format(self, record: logging.LogRecord) -> str:
    entry = {
        "severity": record.levelname,
        "message": record.getMessage(),
        "logger": record.name,
    }
    entry.update(getattr(record, "fields", {}))
    if record.exc_info:
      entry["exception"] = self.formatException(record.exc_info)
    return json.dumps(entry, default=str)


def configure_json_logging(level: str = "INFO") -> None:
  handler = logging.StreamHandler()
  handler.setFormatter(JsonFormatter())
  root = logging.getLogger()
  root.handlers.clear()
  root.addHandler(handler)
  root.setLevel(level.upper())


def log_fields(logger: logging.Logger, level: int, message: str,
               **fields) -> None:
  """Emits a structured log line. Never pass raw prompt text as a field --
  on failure paths, log `type(exc).__name__`, not `str(exc)`, since a
  Jinja2 TemplateError's message can echo the offending template text."""
  logger.log(level, message, extra={"fields": fields})
