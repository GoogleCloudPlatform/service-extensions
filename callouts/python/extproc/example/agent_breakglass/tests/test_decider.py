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

"""Pure unit tests for the Decider policy engine. No gRPC server, no
Firestore, no network."""
import unittest

from decider import Decider, Decision
from findings import DetectionSource, Finding


def _finding(agent_id="agent-1", severity=80, source=DetectionSource.VERTEX_ANOMALY_DETECTION):
    return Finding(agent_id=agent_id, severity=severity, rationale="test", source=source, source_finding_id="f-1")


class TestDecider(unittest.TestCase):
    def test_blocks_when_above_threshold(self):
        decider = Decider(dry_run=False, exempt_agents=(), min_severity_vertex_anomaly=70,
                           min_severity_scc=60, min_severity_wiz=60)
        result = decider.evaluate(_finding(severity=80))
        self.assertEqual(result.decision, Decision.BLOCK)

    def test_skips_below_threshold(self):
        decider = Decider(dry_run=False, exempt_agents=(), min_severity_vertex_anomaly=70,
                           min_severity_scc=60, min_severity_wiz=60)
        result = decider.evaluate(_finding(severity=50))
        self.assertEqual(result.decision, Decision.BELOW_THRESHOLD)

    def test_dry_run_short_circuits_before_actuation(self):
        decider = Decider(dry_run=True, exempt_agents=(), min_severity_vertex_anomaly=0,
                           min_severity_scc=0, min_severity_wiz=0)
        result = decider.evaluate(_finding(severity=99))
        self.assertEqual(result.decision, Decision.DRY_RUN_SKIPPED)

    def test_exempt_agent_never_blocked(self):
        decider = Decider(dry_run=False, exempt_agents=("agent-1",), min_severity_vertex_anomaly=0,
                           min_severity_scc=0, min_severity_wiz=0)
        result = decider.evaluate(_finding(agent_id="agent-1", severity=99))
        self.assertEqual(result.decision, Decision.EXEMPT)

    def test_thresholds_are_per_source(self):
        decider = Decider(dry_run=False, exempt_agents=(), min_severity_vertex_anomaly=90,
                           min_severity_scc=30, min_severity_wiz=60)
        r1 = decider.evaluate(_finding(severity=50, source=DetectionSource.VERTEX_ANOMALY_DETECTION))
        self.assertEqual(r1.decision, Decision.BELOW_THRESHOLD)
        r2 = decider.evaluate(_finding(severity=50, source=DetectionSource.SECURITY_COMMAND_CENTER))
        self.assertEqual(r2.decision, Decision.BLOCK)


if __name__ == "__main__":
    unittest.main()
