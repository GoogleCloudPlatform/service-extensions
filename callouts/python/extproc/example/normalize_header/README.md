# Normalize Header Callout

This callout server normalizes incoming HTTP requests by deriving and injecting
a new header based on the request’s host. It demonstrates how to enrich requests
with computed metadata and influence routing decisions in a Layer 7 load balancer.

The server inspects the `:authority` (host) header and determines the client
device type (mobile, tablet, or desktop). It then injects a
`client-device-type` header into the request and clears the route cache so the
load balancer can re-evaluate routing using the new header.

Use this callout when you need **request normalization**, **device-based routing**,
or **header enrichment** without modifying upstream services.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server reads the `:authority` header (host) from the incoming request.
3. The host value is evaluated to determine the device type:
   - `m.example.com` → mobile
   - `t.example.com` → tablet
   - anything else → desktop
4. A new header `client-device-type` is added with the computed value.
5. The route cache is cleared to ensure routing decisions consider the new header.
6. The modified request continues through the load balancer.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Reads `:authority`, determines device type, injects `client-device-type` header, and clears route cache. |

---

## Run

```bash
cd callouts/python
python -m extproc.example.normalize_header.service_callout_example
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
| **Mobile host** | Requests to `m.example.com` receive `client-device-type: mobile`. |
| **Tablet host** | Requests to `t.example.com` receive `client-device-type: tablet`. |
| **Other hosts** | All other hosts receive `client-device-type: desktop`. |
| **Missing host header** | No mutation is applied if `:authority` is not present. |
| **Route recalculation** | Route cache is cleared so routing decisions can use the new header. |

---

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/normalize_header/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/NormalizeHeader.java)