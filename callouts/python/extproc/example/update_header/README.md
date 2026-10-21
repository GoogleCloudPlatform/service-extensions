# Update Header Callout

This callout server updates existing HTTP headers (or adds them if missing) for
both requests and responses. It demonstrates how to perform controlled header
mutations using overwrite semantics in a Layer 7 load balancer.

The server modifies headers by using an append action that overwrites existing
values if present, ensuring consistent header values across the request/response
lifecycle.

Use this callout when you need **header normalization**, **value overriding**, or
**consistent header enforcement** without modifying backend services.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `on_request_headers` callback:
   - Adds or updates the `header-request` header.
   - Uses overwrite semantics to replace any existing value.
   - Clears the route cache to ensure routing decisions consider the updated header.
3. When the backend responds, the load balancer sends another `ProcessingRequest`
   with `response_headers`.
4. The server's `on_response_headers` callback:
   - Adds or updates the `header-response` header.
   - Uses overwrite semantics to replace any existing value.
5. The modified response is returned to the client.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Adds or overwrites `header-request` header and clears route cache. |
| `on_response_headers` | Adds or overwrites `header-response` header. |

---

## Run

```bash
cd callouts/python
python -m extproc.example.update_header.service_callout_example
```
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
| **Request header update** | `header-request` is added or overwritten with `request-new-value`. |
| **Response header update** | `header-response` is added or overwritten with `response-new-value`. |
| **Existing header present** | Existing values are replaced due to overwrite semantics. |
| **Header missing** | Header is added if it does not already exist. |
| **Route recalculation** | Route cache is cleared after request mutation. |

---

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/update_header/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/UpdateHeader.java)