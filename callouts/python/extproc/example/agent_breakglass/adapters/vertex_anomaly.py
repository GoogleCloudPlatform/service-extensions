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

"""Polling adapter for Vertex AI's anomaly-detection signals. A Cloud
Scheduler job periodically hits the ingestion app's /poll/anomaly-detection
endpoint, which calls this adapter to query the Vertex AI API and normalize
any anomalies found into `Finding`s.
"""
import logging

import requests

from findings import DetectionSource, Finding


class VertexAnomalyAdapter:
    def __init__(self, poll_endpoint: str, timeout_seconds: float = 10.0):
        self.poll_endpoint = poll_endpoint
        self.timeout_seconds = timeout_seconds

    def poll(self) -> list:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())

        try:
            resp = requests.get(
                self.poll_endpoint,
                headers={"Authorization": f"Bearer {credentials.token}"},
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
        except requests.RequestException:
            logging.exception("vertex anomaly detection poll failed")
            return []

        findings = []
        for anomaly in resp.json().get("anomalies", []):
            try:
                findings.append(Finding(
                    agent_id=anomaly["resourceName"],
                    severity=int(anomaly.get("severityScore", 0)),
                    rationale=anomaly.get("description", "vertex anomaly detected"),
                    source=DetectionSource.VERTEX_ANOMALY_DETECTION,
                    source_finding_id=anomaly.get("findingId", anomaly["resourceName"]),
                ))
            except (KeyError, ValueError):
                logging.warning("skipping malformed vertex anomaly payload: %r", anomaly)
        return findings
