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

import logging
import os
from http.server import ThreadingHTTPServer
from extauthz.example.kill_switch.kill_switch_core import Decider, Actuator
from extauthz.example.kill_switch.kill_switch_webhooks import WebhookHandler
from extauthz.example.kill_switch.kill_switch_callout import InMemoryStateStore, RedisStateStore

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    store_type = os.environ.get("STATE_STORE_TYPE", "memory").lower()
    if store_type == "redis":
        logging.info("Starting Webhooks in PRODUCTION mode (RedisStateStore)")
        redis_host = os.environ.get("REDIS_HOST")
        if not redis_host:
            raise ValueError("REDIS_HOST environment variable is required in production mode.")
        redis_port = int(os.environ.get("REDIS_PORT", 6379))
        state_store = RedisStateStore(host=redis_host, port=redis_port)
    else:
        logging.info("Starting Webhooks in DEVELOPMENT mode (InMemoryStateStore)")
        logging.warning(
            "DEV MODE: InMemoryStateStore is not shared with the ext_authz process. "
            "Blocks triggered here will not be enforced at the gateway. "
            "Use STATE_STORE_TYPE=redis for end-to-end testing."
        )
        state_store = InMemoryStateStore()

    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    exempt_agents_raw = os.environ.get("EXEMPT_AGENTS", "")
    exempt_agents = {a.strip() for a in exempt_agents_raw.split(",") if a.strip()}
    severity_thresholds = {
        "scc": os.environ.get("SCC_THRESHOLD", "HIGH"),
        "wiz": os.environ.get("WIZ_THRESHOLD", "CRITICAL"),
        "vertex": os.environ.get("VERTEX_THRESHOLD", "MEDIUM"),
    }
    
    WebhookHandler.state_store = state_store
    WebhookHandler.decider = Decider(dry_run=dry_run, exempt_agents=exempt_agents, severity_thresholds=severity_thresholds)
    WebhookHandler.actuator = Actuator(state_store=state_store)

    port = int(os.environ.get("PORT", 8080))
    httpd = ThreadingHTTPServer(('0.0.0.0', port), WebhookHandler)
    
    logging.info(f"Starting Kill Switch HTTP Webhook Server on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down HTTP server...")
        httpd.server_close()
