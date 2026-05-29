# Copyright 2026 Google LLC.
# Licensed under the Apache License, Version 2.0

import logging
import os
from extauthz.example.kill_switch.kill_switch_callout import KillSwitchCalloutServer, InMemoryStateStore, RedisStateStore

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    store_type = os.environ.get("STATE_STORE_TYPE", "memory").lower()
    if store_type == "redis":
        logging.info("Starting in PRODUCTION mode (RedisStateStore)")
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        if not redis_host:
            raise ValueError("REDIS_HOST environment variable is missing in production mode.")
        redis_port = int(os.environ.get("REDIS_PORT", 6379))
        active_state_store = RedisStateStore(host=redis_host, port=redis_port)
    else:
        logging.info("Starting in DEVELOPMENT mode (InMemoryStateStore)")
        active_state_store = InMemoryStateStore()

    port = int(os.environ.get("PORT", 8080))

    logging.info(f"Starting Kill Switch gRPC ext_authz Server on port {port}...")
    
    KillSwitchCalloutServer(
        state_store=active_state_store, 
        address=('0.0.0.0', port)
    ).run()
