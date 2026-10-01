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

"""
Kill Switch Agent Verification CLI

This administrative utility allows Security Operations and Platform Engineers to 
manually verify the current isolation status of a given SPIFFE ID against the 
Kill Switch External Authorization (ext_authz) gRPC server.

Usage Examples:
    1. Local Development Testing (Plaintext gRPC):
       python3 agent_verification_cli.py --env local \
           --target-url "localhost:8080" \
           --agent-id "spiffe://domain.com/agent-123"

    2. Cloud Production Testing (Secure gRPC with GCP Identity Token):
       python3 agent_verification_cli.py --env cloud \
           --target-url "kill-switch-ext-authz-xxxx.a.run.app:443" \
           --agent-id "spiffe://domain.com/agent-123"

Prerequisites for Local mode:
    - Ensure the local gRPC server is running in a separate terminal.
    - Run: `python3 -m extauthz.example.kill_switch.run_authz` from the project root.

Prerequisites for Cloud mode:
    - Active gcloud CLI session (run `gcloud auth login`).
    - The executing principal must possess the 'Cloud Run Invoker' IAM role.
"""

import argparse
import logging
import subprocess
import os

os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_TRACE"] = "none"

import grpc
from envoy.service.auth.v3 import external_auth_pb2, external_auth_pb2_grpc, attribute_context_pb2

def get_gcp_identity_token() -> str:
    """Fetches the GCP identity token for secure Cloud Run authentication."""
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-identity-token"])
        return token.decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        logging.error("Failed to retrieve GCP identity token. Ensure you are authenticated via gcloud.")
        raise e

def create_spiffe_request(agent_id: str) -> external_auth_pb2.CheckRequest:
    """Constructs the Envoy ext_authz CheckRequest with the target SPIFFE ID."""
    return external_auth_pb2.CheckRequest(
        attributes=attribute_context_pb2.AttributeContext(
            request=attribute_context_pb2.AttributeContext.Request(
                http=attribute_context_pb2.AttributeContext.HttpRequest(
                    headers={"x-spiffe-id": agent_id}
                )
            )
        )
    )

def main():
    parser = argparse.ArgumentParser(description="Kill Switch gRPC Verification Client")
    parser.add_argument(
        "--env", 
        choices=["local", "cloud"], 
        required=True, 
        help="Target environment: 'local' (plaintext) or 'cloud' (secure gRPC with GCP Auth)."
    )
    parser.add_argument(
        "--agent-id", 
        required=True, 
        help="The SPIFFE ID of the agent to verify."
    )
    parser.add_argument(
        "--target-url", 
        required=True, 
        help="The target URL (e.g., 'localhost:8080' or 'kill-switch-ext-authz-xxx.a.run.app:443')."
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    logging.info(f"Initializing verification for agent: {args.agent_id}")
    logging.info(f"Targeting environment: {args.env.upper()} at {args.target_url}")

    try:
        if args.env == "cloud":
            logging.info("Acquiring GCP credentials...")
            ssl_credentials = grpc.ssl_channel_credentials()
            token = get_gcp_identity_token()
            call_credentials = grpc.metadata_call_credentials(
                lambda context, callback: callback((('authorization', f'Bearer {token}'),), None)
            )
            channel_credentials = grpc.composite_channel_credentials(ssl_credentials, call_credentials)
            channel = grpc.secure_channel(args.target_url, channel_credentials)
        else:
            channel = grpc.insecure_channel(args.target_url)

        stub = external_auth_pb2_grpc.AuthorizationStub(channel)
        request = create_spiffe_request(args.agent_id)

        logging.info("Transmitting gRPC CheckRequest...")
        response = stub.Check(request)

        # Output evaluation
        if response.HasField("denied_response"):
            logging.warning("[RESULT: BLOCKED] The agent is actively isolated by the Kill Switch.")
            logging.warning(f"[DETAILS] HTTP Status: {response.denied_response.status.code}")
            logging.warning(f"[DETAILS] Server Message: {response.denied_response.body.strip()}")
        else:
            logging.info("[RESULT: ALLOWED] The agent is not present in the blocklist.")
            if response.HasField("ok_response"):
                for header in response.ok_response.headers:
                    logging.info(f"[HEADER INJECTED] {header.header.key}: {header.header.value}")

    except grpc.RpcError as e:
        logging.error(f"gRPC communication failure: {e.details()} (Code: {e.code()})")
    except Exception as e:
        logging.error(f"Unexpected execution error: {e}")

if __name__ == '__main__':
    main()
