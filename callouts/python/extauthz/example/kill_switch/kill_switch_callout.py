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

import logging
import traceback
import sys
import os

try:
    import redis
except ImportError:
    redis = None

from extauthz.service.callout_server import CalloutServerAuth
from extauthz.service.callout_tools import allow_request, deny_request
from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.type.v3 import http_status_pb2
from grpc import ServicerContext

class InMemoryStateStore:
    """Mock state store for local development and unit testing."""
    def __init__(self):
        self._blocked = set()

    def is_blocked(self, agent_id: str) -> bool:
        return agent_id in self._blocked

    def block_agent(self, agent_id: str) -> None:
        self._blocked.add(agent_id)

class RedisStateStore:
    """Production state store connected to Google Cloud Memorystore (Redis)."""
    def __init__(self, host: str, port: int):
        if redis is None:
            raise ImportError("The 'redis' package is required. Run 'pip install redis'.")
        self.client = redis.Redis(host=host, port=port, decode_responses=True)
        self.prefix = "blocked_agent:"

    def is_blocked(self, agent_id: str) -> bool:
        try:
            return self.client.exists(f"{self.prefix}{agent_id}") > 0
        except Exception as e:
            logging.error(f"Error querying Redis State Store: {e}")
            # Fail-open design: allow traffic if cache is unreachable to prevent gateway outages.
            return False

    def block_agent(self, agent_id: str) -> None:
        try:
            # Added without expiry; requires manual removal for unblocking to ensure intentionality of the kill switch action.
            self.client.set(f"{self.prefix}{agent_id}", "BLOCKED")
        except Exception as e:
            logging.error(f"Error updating Redis State Store: {e}")

class KillSwitchCalloutServer(CalloutServerAuth):
    """External authorization server implementing the Agent Kill Switch."""

    def __init__(self, state_store, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state_store = state_store

    def on_check(self, request: auth_pb2.CheckRequest, context: ServicerContext) -> auth_pb2.CheckResponse:
        try:
            agent_id = self.extract_agent_id(request)

            if not agent_id:
                logging.debug("Request allowed: no x-spiffe-id header found.")
                return allow_request()

            if self.state_store.is_blocked(agent_id):
                logging.warning(f"ACCESS DENIED: Agent {agent_id} is in the blocked state store.")
                return deny_request(
                    status_code=http_status_pb2.StatusCode.Forbidden,
                    body="Agent Isolated: Breakglass Kill Switch Engaged\n",
                    headers=[('x-agent-status', 'blocked')]
                )

            logging.debug(f"Request allowed for active agent: {agent_id}")
            return allow_request(headers_to_add=[('x-agent-status', 'active')])

        except Exception as e:
            logging.error(f"Error in Kill Switch Check method: {str(e)}")
            logging.error(traceback.format_exc())
            # Fail-open design
            return allow_request()

    def extract_agent_id(self, request: auth_pb2.CheckRequest) -> str | None:
        """Extracts the agent SPIFFE ID from the validated header."""
        target_header = 'x-spiffe-id'
        
        if hasattr(request.attributes.request.http, 'header_map'):
            for header in request.attributes.request.http.header_map.headers:
                if header.key.lower() == target_header:
                    return header.raw_value.decode('utf-8').strip()

        if hasattr(request.attributes.request.http, 'headers'):
            headers = request.attributes.request.http.headers
            val = headers.get(target_header, '')
            if val:
                return val.strip()

        return None

