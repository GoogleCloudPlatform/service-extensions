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

"""Admin CLI for manual restoration of a contained agent.

Deliberately NOT exposed over gRPC/HTTP -- restoration is a manual,
out-of-band operator action, to avoid any automated "restore" loop that
could undo a containment before an incident is actually resolved.

Usage:
    python3 -m extproc.example.agent_breakglass.admin_cli status <agent_id>
    python3 -m extproc.example.agent_breakglass.admin_cli unblock <agent_id> --confirm
"""
import argparse
import logging
import os
import sys

from extproc.example.agent_breakglass.findings import BlockedStateStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Breakglass admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    status_parser = sub.add_parser("status", help="Check whether an agent is currently blocked")
    status_parser.add_argument("agent_id")

    unblock_parser = sub.add_parser("unblock", help="Manually restore a contained agent")
    unblock_parser.add_argument("agent_id")
    unblock_parser.add_argument(
        "--confirm", action="store_true",
        help="Required. Confirms you have reviewed the block_succeeded audit log and resolved the incident.",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    project_id = os.environ["GCP_PROJECT_ID"]
    collection = os.getenv("FIRESTORE_COLLECTION", "breakglass_blocked_agents")
    state_store = BlockedStateStore(collection_name=collection, cache_ttl_seconds=0, project_id=project_id)

    if args.command == "status":
        blocked = state_store.is_blocked(args.agent_id)
        print(f"{args.agent_id}: {'BLOCKED' if blocked else 'ACTIVE'}")
        return

    if args.command == "unblock":
        if not args.confirm:
            print(
                "Refusing to unblock without --confirm. Review the block_succeeded audit "
                "log entry for this agent_id in Cloud Logging before restoring access.",
                file=sys.stderr,
            )
            sys.exit(1)
        state_store.unblock(args.agent_id)
        logging.info("manual restoration executed: agent_id=%s", args.agent_id)
        print(f"{args.agent_id}: restored to ACTIVE")


if __name__ == "__main__":
    main()
