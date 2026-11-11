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

import base64
import hashlib
import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from extauthz.example.kill_switch.kill_switch_core import Finding, Decider, Actuator, StateStore, Decision

# Guard against oversized request DoS on public endpoints.
MAX_PAYLOAD_SIZE = 10 * 1024 * 1024

class WebhookHandler(BaseHTTPRequestHandler):
    """Handle incoming security events from SCC, Wiz, and Vertex AI."""
    
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

    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_scc(self):
        """Processes Security Command Center findings from a Pub/Sub push subscription."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        if content_length == 0:
            logging.warning("Received webhook request with empty body")
            self.send_response(400)
            self.end_headers()
            return
        if content_length > MAX_PAYLOAD_SIZE:
            self.send_response(413)
            self.end_headers()
            return

        body = self.rfile.read(content_length)
        
        try:
            payload = json.loads(body)
            
            # Handle Pub/Sub Push subscription envelope encapsulation
            if 'message' in payload and 'data' in payload['message']:
                decoded_data = base64.b64decode(payload['message']['data']).decode('utf-8')
                scc_finding = json.loads(decoded_data)
            else:
                scc_finding = payload

            agent_id = scc_finding.get('resourceName')
            if not agent_id:
                logging.warning("SCC finding missing 'resourceName' — ignoring.")
                self.send_response(202)
                self.end_headers()
                return
            finding = Finding(
                agent_id=agent_id,
                severity=scc_finding.get('severity', 'LOW').upper(),
                rationale=scc_finding.get('category', 'No description'),
                source_finding_id=scc_finding.get('id', 'scc-unknown'),
                source='scc'
            )
            self._process_finding(finding)
            self.send_response(202)
        except Exception as e:
            logging.error(f"Error processing SCC webhook: {e}")
            self.send_response(500)
        self.end_headers()

    def _handle_wiz(self):
        """Processes Wiz security findings from an HTTPS webhook."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        if content_length == 0:
            logging.warning("Received webhook request with empty body")
            self.send_response(400)
            self.end_headers()
            return
        if content_length > MAX_PAYLOAD_SIZE:
            self.send_response(413)
            self.end_headers()
            return
        body = self.rfile.read(content_length)
        if not self._validate_wiz_signature(body):
            logging.warning("[SECURITY] Wiz webhook rejected: invalid signature.")
            self.send_response(401)
            self.end_headers()
            return
        try:
            payload = json.loads(body)
            agent_id = payload.get('agent_id') or payload.get('resource')
            if not agent_id:
                logging.warning("Wiz finding missing agent identifier — ignoring.")
                self.send_response(202)
                self.end_headers()
                return
            finding = Finding(
                agent_id=agent_id,
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

    def _validate_wiz_signature(self, body: bytes) -> bool:
        """Validates the HMAC-SHA256 signature sent by Wiz in X-Wiz-Signature."""
        secret = os.environ.get("WIZ_WEBHOOK_SECRET")
        if not secret:
            logging.warning("[SECURITY] WIZ_WEBHOOK_SECRET is not configured — Wiz webhook authentication is disabled.")
            return True
        received_sig = self.headers.get("X-Wiz-Signature", "")
        expected_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received_sig, expected_sig)

    def _handle_vertex_poll(self):
        """Triggered by Cloud Scheduler to poll Vertex AI for anomalous agent behavior."""
        vertex_enabled = os.environ.get("ENABLE_VERTEX_POLLING", "false").lower() == "true"
        
        if not vertex_enabled:
            logging.debug("[VERTEX POLL] Vertex AI polling is disabled. Set ENABLE_VERTEX_POLLING=true to activate.")
            self.send_response(200)
            self.end_headers()
            return

        try:
            from google.cloud import aiplatform
            
            project_id = os.environ.get("GCP_PROJECT_ID")
            location = os.environ.get("GCP_REGION", "us-central1")
            endpoint_id = os.environ.get("VERTEX_ENDPOINT_ID")
            
            if not endpoint_id or not project_id:
                raise ValueError("Missing VERTEX_ENDPOINT_ID or GCP_PROJECT_ID environment variables.")

            aiplatform.init(project=project_id, location=location)
            endpoint = aiplatform.Endpoint(endpoint_id)

            response = endpoint.predict(instances=[{"time_window": "5m"}], timeout=90)

            if hasattr(response, 'predictions'):
                for anomaly in response.predictions:
                    if anomaly.get('is_anomalous'):
                        agent_id = anomaly.get('agent_id')
                        if not agent_id:
                            logging.warning("Vertex anomaly missing 'agent_id' — skipping.")
                            continue
                        finding = Finding(
                            agent_id=agent_id,
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
            self.send_response(500)
            
        self.end_headers()

    def _process_finding(self, finding: Finding):
        """Routes a normalized finding through the Decider and triggers actuation on a BLOCK decision."""
        decision = self.decider.evaluate(finding)
        if decision == Decision.BLOCK:
            logging.warning(f"Blocking agent {finding.agent_id} due to finding from {finding.source}")
            self.actuator.execute_block(finding)
        else:
            logging.info(f"Ignored finding for agent {finding.agent_id}: {decision}")

    def log_message(self, format, *args):
        """Suppress default HTTP request logging to focus on audit logs."""
        pass
