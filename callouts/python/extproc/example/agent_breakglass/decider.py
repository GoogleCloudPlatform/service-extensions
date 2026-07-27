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

"""Decision engine: evaluates a normalized Finding against policy and
returns BLOCK or a reason it was skipped.

  1. Dry-Run Check: if the global dry_run flag is set, log the intended
     action and abort (no actuation).
  2. Exemption Check: agent_id in exempt_agents -> drop the finding.
  3. Severity Threshold: compare against the per-source minimum.
  4. Idempotency: this service is stateless (no dedup ledger) -- duplicate
     findings for an already-blocked agent are expected and must be safe;
     the Actuator's block() is an idempotent upsert.
"""
import logging
from dataclasses import dataclass
from enum import Enum

from extproc.example.agent_breakglass.findings import DetectionSource, Finding

_THRESHOLD_ATTR_BY_SOURCE = {
    DetectionSource.VERTEX_ANOMALY_DETECTION: "min_severity_vertex_anomaly",
    DetectionSource.SECURITY_COMMAND_CENTER: "min_severity_scc",
    DetectionSource.WIZ: "min_severity_wiz",
}


class Decision(str, Enum):
    BLOCK = "block"
    DRY_RUN_SKIPPED = "dry_run_skipped"
    EXEMPT = "exempt"
    BELOW_THRESHOLD = "below_threshold"


@dataclass
class DecisionResult:
    decision: Decision
    finding: Finding


class Decider:
    def __init__(
        self,
        dry_run: bool,
        exempt_agents: tuple,
        min_severity_vertex_anomaly: int,
        min_severity_scc: int,
        min_severity_wiz: int,
    ):
        self.dry_run = dry_run
        self.exempt_agents = exempt_agents
        self.min_severity_vertex_anomaly = min_severity_vertex_anomaly
        self.min_severity_scc = min_severity_scc
        self.min_severity_wiz = min_severity_wiz

    def evaluate(self, finding: Finding) -> DecisionResult:
        if self.dry_run:
            logging.info(
                "dry_run enabled -- would have blocked agent_id=%s severity=%d source=%s",
                finding.agent_id, finding.severity, finding.source.value,
            )
            return DecisionResult(Decision.DRY_RUN_SKIPPED, finding)

        if finding.agent_id in self.exempt_agents:
            logging.info("agent_id=%s is exempt -- dropping finding", finding.agent_id)
            return DecisionResult(Decision.EXEMPT, finding)

        threshold = getattr(self, _THRESHOLD_ATTR_BY_SOURCE[finding.source])
        if finding.severity < threshold:
            logging.info(
                "finding below severity threshold: agent_id=%s severity=%d threshold=%d source=%s",
                finding.agent_id, finding.severity, threshold, finding.source.value,
            )
            return DecisionResult(Decision.BELOW_THRESHOLD, finding)

        return DecisionResult(Decision.BLOCK, finding)
