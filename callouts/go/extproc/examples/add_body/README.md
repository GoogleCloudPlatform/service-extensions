# Add Body Callout (Go)

This callout server demonstrates how to modify HTTP request and response bodies
using a gRPC-based service callout in Go. It showcases how to **replace or inject
new body content** during both request and response processing in a Layer 7 load balancer.

On incoming requests, the server replaces the request body with a new value. On
outgoing responses, it replaces the response body with another predefined value.

Use this callout when you need **payload transformation**, **content rewriting**,
or **body-level control** without modifying backend services.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_body` to the callout server.
2. The server's `HandleRequestBody` handler:
   - Replaces the request body with `new-body-request`.
3. The request continues to the backend service with the modified body.
4. When the backend responds, the load balancer sends a `ProcessingRequest`
   with `response_body`.
5. The server's `HandleResponseBody` handler:
   - Replaces the response body with `new-body-response`.
6. The modified response is returned to the client.

---

## Callbacks / Handlers

| Handler | Behavior |
|---|---|
| `HandleRequestBody` | Replaces the request body with `new-body-request`. |
| `HandleResponseBody` | Replaces the response body with `new-body-response`. |

---

## Run

**Go:**

```bash
cd callouts/go
EXAMPLE_TYPE=add_body go run ./extproc/cmd/example/main.go
```

---

## Test

**Go:**

```bash
cd callouts/go
go test ./extproc/examples/add_body/...
```

This example may also be covered by shared gRPC integration tests depending on
the repository setup.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request body replacement** | Incoming request body is replaced with `new-body-request`. |
| **Response body replacement** | Outgoing response body is replaced with `new-body-response`. |
| **Full mutation** | Both request and response bodies are completely overwritten. |
| **Payload control** | Enables dynamic manipulation of HTTP message bodies. |

---

## Available Languages

- [x] [Go](.) (this directory)
- [ ] Python
- [ ] Java