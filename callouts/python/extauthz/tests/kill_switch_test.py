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

from __future__ import print_function

import os
import datetime
import threading
import time
import json
import urllib.request
from typing import Iterator, Callable, Any, Mapping

from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.service.auth.v3 import attribute_context_pb2 as attr_pb2
from envoy.type.v3 import http_status_pb2
import grpc
import pytest
from http.server import ThreadingHTTPServer
from unittest.mock import patch, MagicMock

from extauthz.service.callout_server import CalloutServerAuth, _addr_to_str
from extauthz.example.kill_switch.kill_switch_callout import KillSwitchCalloutServer, InMemoryStateStore
from extauthz.example.kill_switch.kill_switch_core import Decider, Finding, Decision, Actuator
from extauthz.example.kill_switch.kill_switch_webhooks import WebhookHandler

class NoResponseError(Exception):
    pass

_mock_store = InMemoryStateStore()
_mock_store.block_agent('spiffe://agents.global.org/compromised-agent-123')

default_kwargs: dict = {
    'address': ('localhost', 8453),
    'health_check_address': ('localhost', 8013),
    'state_store': _mock_store
}

_local_test_args: dict = {
    "kwargs": default_kwargs,
    "test_class": KillSwitchCalloutServer
}

def get_plaintext_channel(server: CalloutServerAuth) -> grpc.Channel:
    addr = server.plaintext_address
    return grpc.insecure_channel(_addr_to_str(addr) if addr else '')

def wait_till_server(server_check: Callable[[], bool], timeout: int = 10):
    expiration = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
    while not server_check() and datetime.datetime.now() < expiration:
        time.sleep(1)

def _start_server(server: CalloutServerAuth) -> threading.Thread:
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    wait_till_server(lambda: getattr(server, '_setup', False))
    return thread

def _stop_server(server: CalloutServerAuth, thread: threading.Thread):
    server.shutdown()
    thread.join(timeout=5)

@pytest.fixture(scope='class', name='server')
def setup_server(request) -> Iterator[CalloutServerAuth]:
    params: dict = request.param or {'kwargs': {}, 'test_class': None}
    kwargs: Mapping[str, Any] = default_kwargs | params['kwargs']
    
    server = (params['test_class'] or CalloutServerAuth)(**kwargs)
    try:
        thread = _start_server(server)
        yield server
        _stop_server(server, thread)
    finally:
        del server

def make_request(stub: auth_pb2_grpc.AuthorizationStub, request: auth_pb2.CheckRequest) -> auth_pb2.CheckResponse:
    try:
        return stub.Check(request)
    except Exception as e:
        raise NoResponseError(f"Request failed: {e}")

def create_request_with_spiffe_id(spiffe_id: str | None) -> auth_pb2.CheckRequest:
    headers = {}
    if spiffe_id is not None:
        headers['x-spiffe-id'] = spiffe_id

    return auth_pb2.CheckRequest(
        attributes=attr_pb2.AttributeContext(
            request=attr_pb2.AttributeContext.Request(
                http=attr_pb2.AttributeContext.HttpRequest(
                    headers=headers
                )
            )
        )
    )

# -------------------------------------------------------------------
# 1. gRPC Server Integration Tests (ext_authz behavior)
# -------------------------------------------------------------------
class TestKillSwitchServer(object):
    """Test server functionality for Agent Containment at the Gateway."""

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_blocked_agent_denied(self, server: KillSwitchCalloutServer) -> None:
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            blocked_id = 'spiffe://agents.global.org/compromised-agent-123'
            request = create_request_with_spiffe_id(blocked_id)
            response = make_request(stub, request)

            assert response.HasField('denied_response')
            assert response.denied_response.status.code == http_status_pb2.StatusCode.Forbidden
            assert "Kill Switch Engaged" in response.denied_response.body
            
            denied_headers = {header.header.key: header.header.value for header in response.denied_response.headers}
            assert denied_headers.get('x-agent-status') == 'blocked'

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_active_agent_allowed(self, server: KillSwitchCalloutServer) -> None:
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            active_id = 'spiffe://agents.global.org/secure-agent-999'
            request = create_request_with_spiffe_id(active_id)
            response = make_request(stub, request)

            assert response.HasField('ok_response')
            ok_headers = {header.header.key: header.header.value for header in response.ok_response.headers}
            assert ok_headers.get('x-agent-status') == 'active'

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_missing_spiffe_id_allowed(self, server: KillSwitchCalloutServer) -> None:
        with get_plaintext_channel(server) as channel:
            stub = auth_pb2_grpc.AuthorizationStub(channel)
            request = create_request_with_spiffe_id(None)
            response = make_request(stub, request)
            assert response.HasField('ok_response')

# -------------------------------------------------------------------
# 2. Core Logic Unit Tests (Policy Engine / Decider)
# -------------------------------------------------------------------
class TestKillSwitchCoreLogic:
    """Test the domain logic handling security evaluations."""

    def setup_method(self):
        self.severity_thresholds = {
            "scc": "HIGH",
            "wiz": "CRITICAL",
            "vertex": "MEDIUM"
        }
        self.exempt_agents = {"spiffe://agents.global.org/super-admin-agent"}
        
        self.decider = Decider(
            dry_run=False,
            exempt_agents=self.exempt_agents,
            severity_thresholds=self.severity_thresholds
        )

    def test_decider_blocks_on_threshold_met(self):
        finding = Finding(
            agent_id="spiffe://agents.global.org/target-agent",
            severity="HIGH",
            source="scc",
            rationale="Anomalous behavior detected",
            source_finding_id="scc-123"
        )
        assert self.decider.evaluate(finding) == Decision.BLOCK

    def test_decider_ignores_below_threshold(self):
        finding = Finding(
            agent_id="spiffe://agents.global.org/target-agent",
            severity="LOW",
            source="wiz",
            rationale="Minor misconfiguration",
            source_finding_id="wiz-123"
        )
        assert self.decider.evaluate(finding) == Decision.IGNORE

    def test_decider_honors_exemption_list(self):
        finding = Finding(
            agent_id="spiffe://agents.global.org/super-admin-agent",
            severity="CRITICAL",
            source="wiz",
            rationale="Critical threat detected",
            source_finding_id="wiz-999"
        )
        assert self.decider.evaluate(finding) == Decision.IGNORE

    def test_decider_honors_dry_run_flag(self):
        dry_run_decider = Decider(
            dry_run=True,
            exempt_agents=set(),
            severity_thresholds=self.severity_thresholds
        )
        finding = Finding(
            agent_id="spiffe://agents.global.org/target-agent",
            severity="CRITICAL",
            source="wiz",
            rationale="Critical threat",
            source_finding_id="wiz-000"
        )
        assert dry_run_decider.evaluate(finding) == Decision.IGNORE

# -------------------------------------------------------------------
# 3. Webhook HTTP Server Tests (Ingestion Pipeline)
# -------------------------------------------------------------------
class TestKillSwitchWebhooks:
    """Test the ingestion endpoints for SCC and Wiz."""

    @pytest.fixture(scope='class', autouse=True)
    def http_server(self):
        store = InMemoryStateStore()
        decider = Decider(dry_run=False, exempt_agents=set(), severity_thresholds={"scc": "HIGH"})
        actuator = Actuator(state_store=store)

        WebhookHandler.state_store = store
        WebhookHandler.decider = decider
        WebhookHandler.actuator = actuator

        server = ThreadingHTTPServer(('localhost', 8090), WebhookHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        
        yield store 
        
        server.shutdown()
        thread.join(timeout=2)

    def test_scc_webhook_blocks_high_severity(self, http_server):
        payload = {
            "resourceName": "spiffe://agents.global.org/scc-compromised",
            "severity": "HIGH",
            "category": "Malware Detected",
            "id": "scc-12345"
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request('http://localhost:8090/webhook/scc', data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Content-Length', str(len(data)))

        response = urllib.request.urlopen(req)
        
        assert response.getcode() == 202
        assert http_server.is_blocked("spiffe://agents.global.org/scc-compromised") == True
    
    def test_vertex_poll_disabled_by_default(self, http_server):
        """Test that the Vertex endpoint safely returns 200 when the feature flag is off."""
        req = urllib.request.Request('http://localhost:8090/poll/anomaly-detection', method='POST')
        
        # We explicitly ensure the environment variable is not set
        with patch.dict(os.environ, {}, clear=True):
            response = urllib.request.urlopen(req)
            assert response.getcode() == 200

    def test_vertex_poll_missing_env_vars_returns_500(self, http_server):
        """Test that enabling the flag without configuring the endpoint ID triggers a safe 500 error."""
        req = urllib.request.Request('http://localhost:8090/poll/anomaly-detection', method='POST')
        
        # Turn the flag on, but leave VERTEX_ENDPOINT_ID empty
        env_patch = {
            "ENABLE_VERTEX_POLLING": "true",
            "GCP_PROJECT_ID": "test-project"
        }
        
        with patch.dict(os.environ, env_patch):
            try:
                urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:
                # We expect a 500 Internal Server Error to be safely caught and returned
                assert e.code == 500

    def test_vertex_poll_success_blocks_agent(self, http_server):
        """Mock the Vertex AI response and ensure a detected anomaly blocks the agent."""
        req = urllib.request.Request('http://localhost:8090/poll/anomaly-detection', method='POST')
        
        env_patch = {
            "ENABLE_VERTEX_POLLING": "true",
            "GCP_PROJECT_ID": "test-project",
            "VERTEX_ENDPOINT_ID": "123456789"
        }
        
        # Create a mock representation of the Vertex AI Prediction response
        mock_prediction = {
            "is_anomalous": True,
            "agent_id": "spiffe://agents.global.org/vertex-compromised",
            "severity": "CRITICAL",
            "reason": "Exfiltration pattern detected"
        }
        mock_response = MagicMock()
        mock_response.predictions = [mock_prediction]

        mock_endpoint_instance = MagicMock()
        mock_endpoint_instance.predict.return_value = mock_response

        # We mock the 'google.cloud.aiplatform' library so the test doesn't actually hit the internet
        mock_aiplatform = MagicMock()
        mock_aiplatform.Endpoint.return_value = mock_endpoint_instance

        mock_google_cloud = MagicMock()
        mock_google_cloud.aiplatform = mock_aiplatform

        import sys
        with patch.dict(os.environ, env_patch), patch.dict(sys.modules, {'google': MagicMock(), 'google.cloud': mock_google_cloud, 'google.cloud.aiplatform': mock_aiplatform}):
            response = urllib.request.urlopen(req)
            
            assert response.getcode() == 200
            # Ensure the Decider evaluated the mock prediction and Actuator saved it to the state store
            assert http_server.is_blocked("spiffe://agents.global.org/vertex-compromised") == True
