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

"""Wiz sends HTTPS webhooks directly to the ingestion app's /webhook/wiz
endpoint. This adapter normalizes Wiz's issue/finding payload into a
`Finding`. Webhook authenticity is verified via a shared-secret HMAC
(WIZ_WEBHOOK_SHARED_SECRET) before this adapter is ever invoked -- see
ingestion.py.
"""
import logging

from findings import DetectionSource, Finding

_SEVERITY_MAP = {"INFORMATIONAL": 10, "LOW": 25, "MEDIUM": 50, "HIGH": 75, "CRITICAL": 95}


class WizAdapter:
    def parse_webhook(self, payload: dict):
        issue = payload.get("issue", payload)
        agent_id = (
            issue.get("resourceExternalId")
            or issue.get("entitySnapshot", {}).get("externalId")
            or issue.get("resource_id")
        )
        severity_str = str(issue.get("severity", "MEDIUM")).upper()

        if not agent_id:
            logging.warning("Wiz webhook missing resource identifier: %r", issue)
            return None

        return Finding(
            agent_id=agent_id,
            severity=_SEVERITY_MAP.get(severity_str, 50),
            rationale=issue.get("type", "wiz finding"),
            source=DetectionSource.WIZ,
            source_finding_id=issue.get("id", agent_id),
        )
