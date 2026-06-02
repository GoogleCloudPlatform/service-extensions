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
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Set, Dict

# Explicit severity weighting matrix to evaluate threshold levels numerically
SEVERITY_WEIGHTS = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4
}

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
            logging.info(
                f"[DRY-RUN] Would block agent {finding.agent_id} | "
                f"source={finding.source} severity={finding.severity} rationale={finding.rationale}"
            )
            return Decision.IGNORE

        if finding.agent_id in self.exempt_agents:
            logging.info(f"[EXEMPT] Agent {finding.agent_id} is in the exemption list. Ignoring.")
            return Decision.IGNORE

        # Fetch configured severity thresholds and translate to numeric weights
        required_severity = self.severity_thresholds.get(finding.source, "CRITICAL").upper()
        required_weight = SEVERITY_WEIGHTS.get(required_severity, 4)
        
        finding_severity = finding.severity.upper()
        finding_weight = SEVERITY_WEIGHTS.get(finding_severity, 0)

        # Enforce relative severity threshold check
        if finding_weight < required_weight:
            logging.info(f"[THRESHOLD] Finding ignored. Severity {finding.severity} is below threshold {required_severity}.")
            return Decision.IGNORE

        return Decision.BLOCK

class Actuator:
    """Executes the containment pipeline."""
    def __init__(self, state_store: StateStore):
        self.state_store = state_store

    def execute_block(self, finding: Finding) -> None:
        """Executes multi-layered containment operations."""
        try:
            self.state_store.block_agent(finding.agent_id)
        except Exception as e:
            logging.error(f"BLOCK FAILED — state store write error for agent {finding.agent_id}: {e}")
            return

        # Real-time data plane enforcement trigger
        self._patch_gateway_deny_rule(finding.agent_id)
        
        # Identity plane access revocation
        self._revoke_iap_iam(finding.agent_id)
        
        print(json.dumps({
            "severity": "WARNING",
            "message": "block_succeeded",
            "event_type": "agent_isolation",
            "agent_id": finding.agent_id,
            "source": finding.source,
            "source_finding_id": finding.source_finding_id,
            "rationale": finding.rationale,
        }), file=sys.stdout, flush=True)

    def _patch_gateway_deny_rule(self, agent_id: str) -> None:
        """API client stub to inject dynamic network isolation into Envoy / Gateway."""
        logging.debug(f"[ACTUATOR] STUB: Patching Agent Gateway to deny egress for agent {agent_id}")

    def _revoke_iap_iam(self, agent_id: str) -> None:
        """API client stub to execute asynchronous GCP Identity-Aware Proxy IAM role removals."""
        logging.debug(f"[ACTUATOR] STUB: Revoking IAP IAM roles for agent {agent_id}")
