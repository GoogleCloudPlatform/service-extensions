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

"""HTTP ingestion surface for the three finding sources. Runs as a FastAPI
app in a background thread alongside the ext_proc gRPC callout (see
service_callout_example.py) -- these are control-plane endpoints, not on
the data path the Agent Gateway calls per-request.

Routes:
  POST /webhook/scc                 <- SCC Pub/Sub push subscription
  POST /webhook/wiz                 <- Wiz platform webhook
  POST /poll/anomaly-detection      <- hit by Cloud Scheduler on a cadence
  GET  /healthz
"""
import hmac
import os

from fastapi import FastAPI, Header, HTTPException, Request

from extproc.example.agent_breakglass.actuator import Actuator
from extproc.example.agent_breakglass.adapters.scc import SccAdapter
from extproc.example.agent_breakglass.adapters.vertex_anomaly import (
    VertexAnomalyAdapter)
from extproc.example.agent_breakglass.adapters.wiz import WizAdapter
from extproc.example.agent_breakglass.decider import Decider, Decision


def build_ingestion_app(
    decider: Decider,
    actuator: Actuator,
    scc_adapter: SccAdapter,
    wiz_adapter: WizAdapter,
    vertex_adapter: VertexAnomalyAdapter | None,
) -> FastAPI:
    app = FastAPI(title="agent-breakglass-ingestion")
    wiz_shared_secret = os.environ.get("WIZ_WEBHOOK_SHARED_SECRET")

    def _handle_finding(finding) -> dict:
        if finding is None:
            raise HTTPException(status_code=400, detail="could not normalize finding payload")
        result = decider.evaluate(finding)
        if result.decision == Decision.BLOCK:
            actuation = actuator.contain(finding)
            return {"decision": result.decision.value, "errors": actuation.errors}
        return {"decision": result.decision.value}

    @app.post("/webhook/scc")
    async def scc_webhook(request: Request):
        envelope = await request.json()
        finding = scc_adapter.parse_pubsub_push(envelope)
        return _handle_finding(finding)

    @app.post("/webhook/wiz")
    async def wiz_webhook(request: Request, x_wiz_signature: str | None = Header(default=None)):
        if wiz_shared_secret:
            body = await request.body()
            expected = hmac.new(wiz_shared_secret.encode(), body, "sha256").hexdigest()
            if not x_wiz_signature or not hmac.compare_digest(expected, x_wiz_signature):
                raise HTTPException(status_code=401, detail="invalid webhook signature")
        payload = await request.json()
        finding = wiz_adapter.parse_webhook(payload)
        return _handle_finding(finding)

    @app.post("/poll/anomaly-detection")
    async def poll_anomaly_detection():
        if vertex_adapter is None:
            raise HTTPException(status_code=503, detail="VERTEX_ANOMALY_POLL_ENDPOINT not configured")
        findings = vertex_adapter.poll()
        results = [_handle_finding(f) for f in findings]
        return {"findings_processed": len(results), "results": results}

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app
