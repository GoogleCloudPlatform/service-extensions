# Dynamic Forwarding Callout

This callout server dynamically selects a backend endpoint based on an incoming
HTTP request header. It demonstrates how to use **dynamic metadata** to influence
routing decisions in a Layer 7 load balancer.

The server inspects the `ip-to-return` request header and, if it matches a known
set of IP addresses, forwards traffic to that address. If the header is missing
or contains an unknown value, a default fallback endpoint is used.

Use this callout when you need **header-based routing**, simple traffic steering,
or dynamic backend selection without modifying the load balancer configuration.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `on_request_headers` callback looks for the `ip-to-return`
   header in the incoming request.
3. If the header value matches one of the known IPs (`10.1.10.2` or `10.1.10.3`),
   that IP is selected as the target endpoint.
4. If the header is missing or invalid, the server falls back to the default
   IP `10.1.10.4`.
5. The selected IP is encoded into `dynamic_metadata` using
   `build_dynamic_forwarding_metadata`.
6. The load balancer uses this metadata to route the request to the selected
   backend.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Reads `ip-to-return` header and selects a target IP. Falls back to default if invalid or missing. Returns dynamic metadata for routing. |

---

## Run

```bash
cd callouts/python
python -m extproc.example.dynamic_forwarding.service_callout_example
```

---

## Test

```bash
cd callouts/python
pytest extproc/tests/basic_grpc_test.py
```

This example is covered by the shared gRPC integration tests rather than having
a dedicated test file.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Valid header (known IP)** | If `ip-to-return` matches `10.1.10.2` or `10.1.10.3`, traffic is routed to that IP. |
| **Invalid header value** | If the header value is not recognized, the system falls back to `10.1.10.4`. |
| **Missing header** | If the header is absent, the default IP `10.1.10.4` is used. |
| **Dynamic routing metadata** | The selected IP and port (80) are returned as dynamic metadata for the load balancer to consume. |

---

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/dynamic_forwarding/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/DynamicForwarding.java)