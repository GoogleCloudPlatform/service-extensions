# Copyright 2026 Google LLC.
# Licensed under the Apache License, Version 2.0

"""
Kill Switch Agent Unblock CLI

This administrative utility allows Security Operations and Platform Engineers
to safely restore an isolated agent by removing its entry from the Kill Switch
Blocked State Store (Redis).

The CLI connects directly to the Redis instance used by the Kill Switch
service and deletes the key corresponding to the blocked agent.

Safety Guarantees:
    - Requires explicit confirmation by default (unless --yes is provided).
    - Logs a structured "unblock_succeeded" event for audit trail purposes.

Usage Examples:
    1. Using environment variables for Redis connection:
       export REDIS_HOST="10.0.0.5"
       export REDIS_PORT="6379"

       python3 agent_unblock_cli.py \
           --agent-id "spiffe://domain.com/agent-123"

    2. Passing Redis coordinates explicitly:
       python3 agent_unblock_cli.py \
           --agent-id "spiffe://domain.com/agent-123" \
           --redis-host "10.0.0.5" \
           --redis-port 6379

    3. Non-interactive mode (CI / runbook automation):
       python3 agent_unblock_cli.py \
           --agent-id "spiffe://domain.com/agent-123" \
           --redis-host "10.0.0.5" \
           --redis-port 6379 \
           --yes
"""

import argparse
import logging
import os
import sys

try:
    import redis
except ImportError:
    redis = None

# Must match the prefix used by RedisStateStore in kill_switch_callout.py
REDIS_KEY_PREFIX = "blocked_agent:"


def get_redis_client(host: str, port: int):
    """Initializes and returns a Redis client."""
    if redis is None:
        raise ImportError(
            "The 'redis' package is required. "
            "Install it with 'pip install redis' or ensure it is present in additional-requirements.txt."
        )

    return redis.Redis(host=host, port=port, decode_responses=True)


def unblock_agent(client, agent_id: str) -> bool:
    """
    Removes the blocked state entry for the given agent_id.

    Returns:
        True if a key was deleted, False if no key existed.
    """
    key = f"{REDIS_KEY_PREFIX}{agent_id}"

    if not client.exists(key):
        logging.info(
            "No blocked entry found for agent. Nothing to remove.",
            extra={
                "json_fields": {
                    "event_type": "agent_restoration_noop",
                    "agent_id": agent_id,
                    "reason": "no_blocked_key_found"
                }
            }
        )
        return False

    client.delete(key)

    logging.info(
        "unblock_succeeded",
        extra={
            "json_fields": {
                "event_type": "agent_restoration",
                "agent_id": agent_id,
                "reason": "manual_admin_unblock_cli"
            }
        }
    )
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kill Switch Agent Unblock CLI"
    )
    parser.add_argument(
        "--agent-id",
        required=True,
        help="The SPIFFE ID of the agent to unblock (e.g., 'spiffe://domain.com/agent-123')."
    )
    parser.add_argument(
        "--redis-host",
        default=os.environ.get("REDIS_HOST", "localhost"),
        help="Redis host used by the Kill Switch state store. "
             "Defaults to the REDIS_HOST environment variable or 'localhost'."
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=int(os.environ.get("REDIS_PORT", "6379")),
        help="Redis port used by the Kill Switch state store. "
             "Defaults to the REDIS_PORT environment variable or 6379."
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Non-interactive mode. Skip confirmation prompt and proceed with unblock."
    )
    return parser.parse_args()


def confirm_unblock(agent_id: str) -> None:
    """
    Interactive confirmation prompt to avoid accidental agent restoration.
    """
    prompt = (
        f"You are about to UNBLOCK agent:\n\n"
        f"    {agent_id}\n\n"
        f"This will remove the agent from the Kill Switch Blocked State Store,\n"
        f"allowing the Agent Gateway to accept its requests again.\n\n"
        f"Type the exact agent ID to confirm, or press ENTER to cancel:\n> "
    )

    user_input = input(prompt).strip()

    if user_input != agent_id:
        logging.error("Confirmation mismatch or empty input. Aborting unblock operation.")
        sys.exit(1)


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    if not args.yes:
        confirm_unblock(args.agent_id)

    logging.info(
        "Initializing Redis connection...",
        extra={
            "json_fields": {
                "event_type": "agent_restoration_init",
                "agent_id": args.agent_id,
                "redis_host": args.redis_host,
                "redis_port": args.redis_port
            }
        }
    )

    try:
        client = get_redis_client(args.redis_host, args.redis_port)
        removed = unblock_agent(client, args.agent_id)

        if removed:
            logging.info(
                "[RESULT: UNBLOCKED] The agent has been removed from the Blocked State Store."
            )
        else:
            logging.info(
                "[RESULT: NO-OP] The agent was not present in the Blocked State Store."
            )

    except Exception as e:
        logging.error(f"Failed to unblock agent: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
