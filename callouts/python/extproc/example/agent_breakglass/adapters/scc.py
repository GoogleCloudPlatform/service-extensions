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

"""Security Command Center (SCC) sends finding alerts via a Pub/Sub push
subscription to the ingestion app's /webhook/scc endpoint. This adapter
normalizes the Pub/Sub-wrapped SCC finding payload into a `Finding`.
"""
import base64
import json
import logging

from findings import DetectionSource, Finding

_SEVERITY_MAP = {"LOW": 25, "MEDIUM": 50, "HIGH": 75, "CRITICAL": 95}


class SccAdapter:
    def parse_pubsub_push(self, envelope: dict):
        """`envelope` is the raw Pub/Sub push JSON body: {"message": {"data": "<base64>", ...}}"""
        message = envelope.get("message", {})
        data_b64 = message.get("data")
        if not data_b64:
            logging.warning("SCC pubsub push envelope missing message.data")
            return None

        try:
            raw = base64.b64decode(data_b64)
            payload = json.loads(raw)
        except Exception:
            logging.exception("failed to decode SCC pubsub push payload")
            return None

        finding = payload.get("finding", payload)
        resource_name = finding.get("resourceName") or finding.get("resource_name")
        category = finding.get("category", "")
        severity_str = str(finding.get("severity", "MEDIUM")).upper()

        if not resource_name:
            logging.warning("SCC finding missing resourceName: %r", finding)
            return None

        return Finding(
            agent_id=resource_name,
            severity=_SEVERITY_MAP.get(severity_str, 50),
            rationale=f"SCC finding category={category}",
            source=DetectionSource.SECURITY_COMMAND_CENTER,
            source_finding_id=finding.get("name", finding.get("canonicalName", resource_name)),
        )
