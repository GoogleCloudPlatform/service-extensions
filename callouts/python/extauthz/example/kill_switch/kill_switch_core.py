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
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Set, Dict

class Decision(Enum):
    BLOCK = "BLOCK"
    IGNORE = "IGNORE"

@dataclass
class Finding:
    """Normalized payload for security events (SCC, Wiz, Vertex Anomaly)."""
    agent_id: str
    severity: str
    rationale: str
    source_finding_id: str
    source: str

class StateStore(Protocol):
    """Protocol defining the required methods for the blocked state database."""
    def is_blocked(self, agent_id: str) -> bool: ...
    def block_agent(self, agent_id: str) -> None: ...

class Decider:
    """Evaluates normalized findings against security policies."""
    def __init__(self, dry_run: bool, exempt_agents: Set[str], severity_thresholds: Dict[str, str]):
        self.dry_run = dry_run
        self.exempt_agents = exempt_agents
        self.severity_thresholds = severity_thresholds

    def evaluate(self, finding: Finding) -> Decision:
        if self.dry_run:
            logging.info(f"[DRY-RUN] Block decision aborted for agent: {finding.agent_id}")
            return Decision.IGNORE

        if finding.agent_id in self.exempt_agents:
            logging.info(f"[EXEMPT] Agent {finding.agent_id} is in the exemption list. Ignoring.")
            return Decision.IGNORE

        required_severity = self.severity_thresholds.get(finding.source, "CRITICAL")
        if finding.severity != required_severity:
            logging.info(f"[THRESHOLD] Finding ignored. Severity {finding.severity} is below threshold {required_severity}.")
            return Decision.IGNORE

        return Decision.BLOCK

class Actuator:
    """Executes the containment pipeline."""
    def __init__(self, state_store: StateStore):
        self.state_store = state_store

    def execute_block(self, finding: Finding) -> None:
        """Executes multi-layered containment operations."""
        # 1. State Store update (Cache Edge)
        self.state_store.block_agent(finding.agent_id)
        
        # 2. Gateway Egress Block (Patch)
        self._patch_gateway_deny_rule(finding.agent_id)
        
        # 3. IAP IAM Revocation (Defense in depth)
        self._revoke_iap_iam(finding.agent_id)
        
        # 4. Audit log for manual restoration auditing
        logging.info("block_succeeded", extra={
            "json_fields": {
                "event_type": "agent_isolation",
                "agent_id": finding.agent_id,
                "source": finding.source,
                "rationale": finding.rationale
            }
        })

    def _patch_gateway_deny_rule(self, agent_id: str) -> None:
        """Stub: Implementation for the Gateway/Envoy API call to deny egress immediately."""
        logging.warning(f"[ACTUATOR] STUB: Patching Agent Gateway to deny egress for agent {agent_id}")

    def _revoke_iap_iam(self, agent_id: str) -> None:
        """Stub: Implementation for GCP IAM call to revoke roles/iap.egressor."""
        logging.warning(f"[ACTUATOR] STUB: Revoking IAP IAM roles for agent {agent_id}")
