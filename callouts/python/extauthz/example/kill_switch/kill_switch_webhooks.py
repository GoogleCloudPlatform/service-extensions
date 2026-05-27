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

import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from extauthz.example.kill_switch.kill_switch_core import Finding, Decider, Actuator, StateStore, Decision

class WebhookHandler(BaseHTTPRequestHandler):
    """Handle incoming security events from SCC, Wiz, and Vertex."""
    
    state_store: StateStore = None
    decider: Decider = None
    actuator: Actuator = None

    def do_POST(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == '/webhook/scc':
            self._handle_scc()
        elif parsed_url.path == '/webhook/wiz':
            self._handle_wiz()
        elif parsed_url.path == '/poll/anomaly-detection':
            self._handle_vertex_poll()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_scc(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            logging.warning("Received webhook request with empty body")
            self.send_response(400)
            self.end_headers()
            return
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body)
            finding = Finding(
                agent_id=payload.get('resourceName', 'unknown'),
                severity=payload.get('severity', 'LOW').upper(),
                rationale=payload.get('category', 'No description'),
                source_finding_id=payload.get('id', 'scc-unknown'),
                source='scc'
            )
            self._process_finding(finding)
            self.send_response(202)
        except Exception as e:
            logging.error(f"Error processing SCC webhook: {e}")
            self.send_response(500)
        self.end_headers()

    def _handle_wiz(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            logging.warning("Received webhook request with empty body")
            self.send_response(400)
            self.end_headers()
            return
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body)
            finding = Finding(
                agent_id=payload.get('agent_id', payload.get('resource', 'unknown')),
                severity=payload.get('severity', 'MEDIUM').upper(),
                rationale=payload.get('description', 'Wiz alert'),
                source_finding_id=payload.get('id', 'wiz-unknown'),
                source='wiz'
            )
            self._process_finding(finding)
            self.send_response(202)
        except Exception as e:
            logging.error(f"Error processing Wiz webhook: {e}")
            self.send_response(500)
        self.end_headers()

    def _handle_vertex_poll(self):
        """
        Triggered by Cloud Scheduler to poll Vertex AI for anomalous agent behavior.
        Uses a feature flag to prevent execution until the ML model is fully deployed.
        """
        vertex_enabled = os.environ.get("ENABLE_VERTEX_POLLING", "false").lower() == "true"
        
        if not vertex_enabled:
            logging.debug("[VERTEX POLL] Vertex AI polling is disabled. Set ENABLE_VERTEX_POLLING=true to activate.")
            self.send_response(200)
            self.end_headers()
            return

        try:
            # Lazy import to avoid loading heavy ML libraries globally
            from google.cloud import aiplatform
            
            project_id = os.environ.get("GCP_PROJECT_ID")
            location = os.environ.get("GCP_REGION", "us-central1")
            endpoint_id = os.environ.get("VERTEX_ENDPOINT_ID")
            
            if not endpoint_id or not project_id:
                raise ValueError("Missing VERTEX_ENDPOINT_ID or GCP_PROJECT_ID environment variables.")

            # Initialize the Vertex AI client and target the custom anomaly detection model
            aiplatform.init(project=project_id, location=location)
            endpoint = aiplatform.Endpoint(endpoint_id)

            # Query the model for anomalies in the last 5 minutes (matching Cloud Scheduler frequency)
            response = endpoint.predict(instances=[{"time_window": "5m"}])

            if hasattr(response, 'predictions'):
                for anomaly in response.predictions:
                    if anomaly.get('is_anomalous'):
                        finding = Finding(
                            agent_id=anomaly.get('agent_id', 'unknown'),
                            severity=anomaly.get('severity', 'MEDIUM').upper(),
                            rationale=anomaly.get('reason', 'Vertex ML Anomaly Detected'),
                            source_finding_id=anomaly.get('prediction_id', 'vertex-unknown'),
                            source='vertex'
                        )
                        self._process_finding(finding)

            self.send_response(200)
            
        except ImportError:
            logging.error("Failed to import google.cloud.aiplatform. Add 'google-cloud-aiplatform' to additional-requirements.txt.")
            self.send_response(500)
        except Exception as e:
            logging.error(f"Error querying Vertex AI: {e}")
            # Return 500 so Cloud Scheduler logs the failure and can retry
            self.send_response(500)
            
        self.end_headers()

    def _process_finding(self, finding: Finding):
        decision = self.decider.evaluate(finding)
        if decision == Decision.BLOCK:
            logging.warning(f"Blocking agent {finding.agent_id} due to finding from {finding.source}")
            self.actuator.execute_block(finding)
        else:
            logging.info(f"Ignored finding for agent {finding.agent_id}: {decision}")

    def log_message(self, format, *args):
        """Suppress default HTTP request logging to focus on audit logs."""
        pass

