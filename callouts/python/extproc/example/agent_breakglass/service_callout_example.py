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

"""Agent Breakglass callout: a pure ext_proc adapter used as an
authorization extension.

Real-time containment for compromised AI agents. Security detectors
(Vertex Anomaly Detection, Security Command Center, Wiz) post findings to
a small ingestion HTTP app running alongside this callout; a policy engine
(Decider) evaluates them and, on a BLOCK decision, an Actuator marks the
agent BLOCKED in a Firestore-backed Blocked State Store. From that point
on, `on_request_headers` denies every request from that agent at the
gateway boundary with an immediate 403 -- within seconds, and without
mutating any persistent IAM policy or gateway routing configuration.

The Service Extensions `ext_proc` wire protocol is used here (rather than
`ext_authz`) because it's supported for authorization extensions too and
lets this callout share the same `extproc.service.callout_server`
framework as the other examples in this collection: deny by returning an
`ImmediateResponse` from `on_request_headers`, allow by returning `None`.

Unlike the other two examples in this collection, this callout defaults to
**fail-closed**: if the Blocked State Store lookup itself fails (Firestore
outage, network partition), the request is denied rather than allowed. An
unreachable kill switch must not silently become a bypass for a real
containment.

`agent_breakglass` owns:
  * the Decider policy engine (dry-run -> exemption -> per-source severity
    threshold) and the two-stage Actuator (state-store block, then IAP IAM
    revocation), both driven by the ingestion HTTP app (decider.py,
    actuator.py, ingestion.py, adapters/)
  * the Blocked State Store, Firestore-backed with a short-TTL local cache
    for the hot path (findings.py)
  * manual-only restoration via admin_cli.py -- there is no automated
    "unblock" path anywhere in this callout

The callout owns:
  * Envoy ext_proc protobuf adapter (via `extproc.service.callout_server`)
  * the hot-path ALLOW/DENY decision in `on_request_headers`
  * booting the ingestion HTTP app in a background thread
"""

import logging
import os
import threading

import uvicorn
from grpc import ServicerContext

from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3.http_status_pb2 import StatusCode

from extproc.service import callout_server
from extproc.service import callout_tools

from extproc.example.agent_breakglass.actuator import Actuator
from extproc.example.agent_breakglass.adapters.scc import SccAdapter
from extproc.example.agent_breakglass.adapters.vertex_anomaly import (
    VertexAnomalyAdapter)
from extproc.example.agent_breakglass.adapters.wiz import WizAdapter
from extproc.example.agent_breakglass.decider import Decider
from extproc.example.agent_breakglass.findings import BlockedStateStore
from extproc.example.agent_breakglass.ingestion import build_ingestion_app

AGENT_ID_HEADER = "x-agent-id"  # falls back to x-spiffe-id if unset


class BreakglassCallout(callout_server.CalloutServer):
    """Ext_proc callout used as an authorization extension: DENY blocked
    agents at the gateway boundary, ALLOW everything else."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        project_id = os.environ["GCP_PROJECT_ID"]
        # NOTE the default here is the OPPOSITE of the other two examples
        # in this collection: an unreachable kill switch must fail closed.
        self.fail_open = os.getenv("FAIL_OPEN", "false").lower() == "true"

        self.state_store = BlockedStateStore(
            collection_name=os.getenv("FIRESTORE_COLLECTION", "breakglass_blocked_agents"),
            cache_ttl_seconds=int(os.getenv("STATE_CACHE_TTL_SECONDS", "5")),
            project_id=project_id,
        )

        decider = Decider(
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
            exempt_agents=tuple(a.strip() for a in os.getenv("EXEMPT_AGENTS", "").split(",") if a.strip()),
            min_severity_vertex_anomaly=int(os.getenv("MIN_SEVERITY_VERTEX_ANOMALY", "70")),
            min_severity_scc=int(os.getenv("MIN_SEVERITY_SCC", "60")),
            min_severity_wiz=int(os.getenv("MIN_SEVERITY_WIZ", "60")),
        )
        actuator = Actuator(
            state_store=self.state_store,
            iap_egressor_role=os.getenv("IAP_EGRESSOR_ROLE", "roles/iap.egressor"),
            mcp_resource_list=tuple(r.strip() for r in os.getenv("MCP_RESOURCE_LIST", "").split(",") if r.strip()),
            callout_timeout_seconds=float(os.getenv("CALLOUT_TIMEOUT_SECONDS", "10")),
        )
        vertex_poll_endpoint = os.getenv("VERTEX_ANOMALY_POLL_ENDPOINT", "")
        ingestion_app = build_ingestion_app(
            decider=decider,
            actuator=actuator,
            scc_adapter=SccAdapter(),
            wiz_adapter=WizAdapter(),
            vertex_adapter=VertexAnomalyAdapter(vertex_poll_endpoint) if vertex_poll_endpoint else None,
        )
        ingestion_port = int(os.getenv("INGESTION_HTTP_PORT", "8090"))
        threading.Thread(
            target=lambda: uvicorn.run(ingestion_app, host="0.0.0.0", port=ingestion_port, log_level="warning"),
            daemon=True,
        ).start()
        logging.info("Ingestion HTTP app listening on :%d", ingestion_port)

    # ------------------------------------------------------------------ phase

    def on_request_headers(
        self,
        headers: service_pb2.HttpHeaders,
        context: ServicerContext,
    ) -> service_pb2.ProcessingResponse | None:
        agent_id = ""
        for h in headers.headers.headers:
            key = h.key.lower()
            if key in (AGENT_ID_HEADER, "x-spiffe-id"):
                value = (h.raw_value or h.value.encode("utf-8")).decode("utf-8", errors="replace")
                if key == AGENT_ID_HEADER or not agent_id:
                    agent_id = value
                if key == AGENT_ID_HEADER:
                    break

        if not agent_id:
            # No identity to check -- the kill switch has nothing to say
            # here; other gateway authn/z controls remain responsible.
            return None

        try:
            blocked = self.state_store.is_blocked(agent_id)
        except Exception:
            logging.exception("Blocked State Store lookup failed for agent_id=%s", agent_id)
            if self.fail_open:
                return None
            return callout_tools.header_immediate_response(StatusCode.InternalServerError)

        if blocked:
            logging.info("denied request from blocked agent_id=%s", agent_id)
            return callout_tools.header_immediate_response(StatusCode.Forbidden)

        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    BreakglassCallout(disable_tls=True).run()
