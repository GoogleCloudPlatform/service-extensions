# Dynamic Forwarding Callout (Go)

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

## Callbacks / Handlers

| Handler | Behavior |
|---|---|
| `HandleRequestHeaders` | Injects dynamic metadata with selected backend IP. |

---

## Run

```bash
cd callouts/go
EXAMPLE_TYPE=dynamic_forwarding go run ./extproc/cmd/example/main.go
```

---

## Test

```bash
cd callouts/go
go test ./extproc/examples/dynamic_forwarding/...
```

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Header present** | Uses provided IP for routing. |
| **Header missing** | Falls back to default backend. |
| **Dynamic routing** | Enables runtime traffic steering. |

---

## Available Languages

- [x] [Go](.) (this directory)
- [ ] Python
- [ ] Java