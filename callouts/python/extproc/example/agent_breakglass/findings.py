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

"""Normalized Finding contract, shared by all three ingestion adapters, and
the Firestore-backed Blocked State Store the ext_proc hot path reads on
every request.
"""
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DetectionSource(str, Enum):
    VERTEX_ANOMALY_DETECTION = "vertex_anomaly_detection"
    SECURITY_COMMAND_CENTER = "scc"
    WIZ = "wiz"


@dataclass
class Finding:
    agent_id: str
    severity: int  # 0-100, higher = more severe
    rationale: str
    source: DetectionSource
    source_finding_id: str


class BlockedStateStore:
    """The single source of truth for "is agent X currently contained".

    Backed by Firestore. The ext_proc `Check` path is on the hot path for
    every request the Agent Gateway forwards, so a short-TTL in-process
    cache sits in front of Firestore reads. Writes (block/unblock) bypass
    the cache and proactively invalidate the local entry so the new state
    is visible immediately rather than waiting out the TTL.
    """

    def __init__(self, collection_name: str, cache_ttl_seconds: int, project_id: str):
        from google.cloud import firestore  # lazy import

        self._client = firestore.Client(project=project_id)
        self._collection = self._client.collection(collection_name)
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict = {}  # agent_id -> (blocked: bool, cached_at: float)
        self._lock = threading.Lock()

    def is_blocked(self, agent_id: str) -> bool:
        with self._lock:
            cached = self._cache.get(agent_id)
            if cached is not None and (time.time() - cached[1]) < self._cache_ttl_seconds:
                return cached[0]

        doc = self._collection.document(agent_id).get()
        blocked = bool(doc.exists and doc.to_dict().get("blocked", False))
        with self._lock:
            self._cache[agent_id] = (blocked, time.time())
        return blocked

    def block(self, agent_id: str, reason: str, source_finding_id: str) -> None:
        self._collection.document(agent_id).set({
            "blocked": True,
            "reason": reason,
            "source_finding_id": source_finding_id,
            "blocked_at": time.time(),
        })
        self._invalidate(agent_id, blocked=True)

    def unblock(self, agent_id: str) -> None:
        """Manual restoration only -- never called by the Decider."""
        self._collection.document(agent_id).delete()
        self._invalidate(agent_id, blocked=False)

    def _invalidate(self, agent_id: str, blocked: bool) -> None:
        with self._lock:
            self._cache[agent_id] = (blocked, time.time())
