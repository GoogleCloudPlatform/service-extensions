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
from typing import Protocol

SEVERITY_WEIGHTS = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4
}

VALID_SEVERITIES = frozenset(SEVERITY_WEIGHTS)

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
    def __init__(self, dry_run: bool, exempt_agents: set[str], severity_thresholds: dict[str, str]):
        self.dry_run = dry_run
        self.exempt_agents = exempt_agents
        self.severity_thresholds = severity_thresholds
        invalid = {v.upper() for v in severity_thresholds.values()} - VALID_SEVERITIES
        if invalid:
            logging.warning(f"Unknown severity threshold value(s) {invalid} — will never match any finding.")

    def evaluate(self, finding: Finding) -> Decision:
        # Dry-run mode: log intent but skip enforcement.
        if self.dry_run:
            logging.info(
                f"[DRY-RUN] Would block agent {finding.agent_id} | "
                f"source={finding.source} severity={finding.severity} rationale={finding.rationale}"
            )
            return Decision.IGNORE

        # Skip agents explicitly exempted by policy.
        if finding.agent_id in self.exempt_agents:
            logging.info(f"[EXEMPT] Agent {finding.agent_id} is in the exemption list. Ignoring.")
            return Decision.IGNORE

        required_severity = self.severity_thresholds.get(finding.source, "CRITICAL").upper()
        required_weight = SEVERITY_WEIGHTS.get(required_severity, 4)
        # Unknown severities default to weight 0, ensuring they never meet any threshold.
        finding_weight = SEVERITY_WEIGHTS.get(finding.severity.upper(), 0)

        if finding_weight < required_weight:
            logging.info(f"[THRESHOLD] Finding ignored. Severity {finding.severity} is below threshold {required_severity}.")
            return Decision.IGNORE

        return Decision.BLOCK

class Actuator:
    """Executes the containment actuation pipeline on a BLOCK decision."""
    def __init__(self, state_store: StateStore):
        self.state_store = state_store

    def execute_block(self, finding: Finding) -> None:
        """Writes the agent to the blocked state store and emits a structured audit log."""
        try:
            self.state_store.block_agent(finding.agent_id)
        except Exception as e:
            logging.error(f"BLOCK FAILED — state store write error for agent {finding.agent_id}: {e}")
            return

        # Audit log written only after confirmed state store write.
        print(json.dumps({
            "severity": "WARNING",
            "message": "block_succeeded",
            "event_type": "agent_isolation",
            "agent_id": finding.agent_id,
            "source": finding.source,
            "source_finding_id": finding.source_finding_id,
            "rationale": finding.rationale,
        }), file=sys.stdout, flush=True)
