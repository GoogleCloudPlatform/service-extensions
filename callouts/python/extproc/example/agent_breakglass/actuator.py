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

"""Actuator: executes containment when the Decider returns BLOCK.

Two-stage pipeline:
  1. Gateway Egress Block (fastest time-to-mitigate): write the agent as
     BLOCKED in the Blocked State Store, which the callout's
     `on_request_headers` reads on every request. This is what actually
     stops traffic, without mutating any persistent IAM policy or gateway
     routing configuration.
  2. IAP IAM Revocation (defense-in-depth): remove the agent principal from
     roles/iap.egressor on all registered MCP servers/endpoints, so even a
     request that somehow bypasses the gateway still can't reach protected
     resources.

Both stages are idempotent (safe to run twice for duplicate findings) and
produce an immutable structured audit log entry, the sole source of truth
used for manual restoration.
"""
import logging
import time
from dataclasses import dataclass

from findings import BlockedStateStore, Finding


@dataclass
class ActuationResult:
    agent_id: str
    state_store_updated: bool
    iam_revoked_resources: list
    errors: list


class IamRevocationError(Exception):
    pass


class Actuator:
    def __init__(
        self,
        state_store: BlockedStateStore,
        iap_egressor_role: str,
        mcp_resource_list: tuple,
        callout_timeout_seconds: float,
    ):
        self.state_store = state_store
        self.iap_egressor_role = iap_egressor_role
        self.mcp_resource_list = mcp_resource_list
        self.callout_timeout_seconds = callout_timeout_seconds

    def contain(self, finding: Finding) -> ActuationResult:
        errors: list = []

        state_store_updated = False
        try:
            self.state_store.block(
                agent_id=finding.agent_id,
                reason=finding.rationale,
                source_finding_id=finding.source_finding_id,
            )
            state_store_updated = True
        except Exception as exc:  # noqa: BLE001
            logging.exception("failed to write Blocked State Store entry")
            errors.append(f"state_store: {exc}")

        # Best-effort defense-in-depth: a failure here does NOT roll back
        # stage 1 -- the gateway-level block already stops traffic.
        revoked: list = []
        for resource in self.mcp_resource_list:
            try:
                self._revoke_iap_egressor(resource, finding.agent_id)
                revoked.append(resource)
            except IamRevocationError as exc:
                logging.exception("IAM revocation failed for resource=%s", resource)
                errors.append(f"iam_revocation[{resource}]: {exc}")

        result = ActuationResult(
            agent_id=finding.agent_id,
            state_store_updated=state_store_updated,
            iam_revoked_resources=revoked,
            errors=errors,
        )
        self._write_audit_log(finding, result)
        return result

    def _revoke_iap_egressor(self, resource: str, agent_id: str) -> None:
        import requests
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
        headers = {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}

        get_url = f"https://cloudresourcemanager.googleapis.com/v1/{resource}:getIamPolicy"
        set_url = f"https://cloudresourcemanager.googleapis.com/v1/{resource}:setIamPolicy"

        try:
            resp = requests.post(get_url, headers=headers, json={}, timeout=self.callout_timeout_seconds)
            resp.raise_for_status()
            policy = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise IamRevocationError(f"getIamPolicy failed: {exc}") from exc

        member = f"serviceAccount:{agent_id}" if "@" in agent_id else agent_id
        changed = False
        for binding in policy.get("bindings", []):
            if binding.get("role") == self.iap_egressor_role and member in binding.get("members", []):
                binding["members"].remove(member)
                changed = True
        if not changed:
            return  # already absent -- idempotent no-op

        try:
            resp = requests.post(
                set_url, headers=headers, json={"policy": policy}, timeout=self.callout_timeout_seconds)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise IamRevocationError(f"setIamPolicy failed: {exc}") from exc

    def _write_audit_log(self, finding: Finding, result: ActuationResult) -> None:
        status = "block_succeeded" if not result.errors else "block_partial_failure"
        logging.info(
            "%s: agent_id=%s severity=%d rationale=%s source=%s source_finding_id=%s "
            "state_store_updated=%s iam_revoked_resources=%s errors=%s timestamp=%f",
            status, finding.agent_id, finding.severity, finding.rationale, finding.source.value,
            finding.source_finding_id, result.state_store_updated, result.iam_revoked_resources,
            result.errors, time.time(),
        )
