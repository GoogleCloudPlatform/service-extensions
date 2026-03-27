# Add Header Callout (Go)

This callout server demonstrates how to modify HTTP request and response headers
using a gRPC-based service callout in Go. It showcases how to **inject custom
headers** into both request and response flows in a Layer 7 load balancer.

On incoming requests, the server adds a custom request header. On outgoing
responses, it adds a custom response header.

Use this callout when you need **header enrichment**, **metadata propagation**,
or **lightweight request/response augmentation**.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `HandleRequestHeaders` handler:
   - Adds the header `header-request: Value-request`.
3. The request continues to the backend service with the updated headers.
4. When the backend responds, the load balancer sends a `ProcessingRequest`
   with `response_headers`.
5. The server's `HandleResponseHeaders` handler:
   - Adds the header `header-response: Value-response`.
6. The modified response is returned to the client.

---

## Callbacks / Handlers

| Handler | Behavior |
|---|---|
| `HandleRequestHeaders` | Adds `header-request: Value-request` to incoming requests. |
| `HandleResponseHeaders` | Adds `header-response: Value-response` to outgoing responses. |

---

## Run

**Go:**

```bash
cd callouts/go
EXAMPLE_TYPE=add_header go run ./extproc/cmd/example/main.go
```

---

## Test

**Go:**

```bash
cd callouts/go
go test ./extproc/examples/add_header/...
```

This example may also be covered by shared gRPC integration tests depending on
the repository setup.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request header addition** | Adds `header-request: Value-request` to all incoming requests. |
| **Response header addition** | Adds `header-response: Value-response` to all outgoing responses. |
| **Non-destructive mutation** | Existing headers are preserved; only new headers are added. |
| **No route cache impact** | Route cache remains unchanged during processing. |

---

## Available Languages

- [x] [Go](.) (this directory)
- [ ] Python
- [ ] Java