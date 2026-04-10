# Basic Callout Server (Go)

This callout server demonstrates a complete example of HTTP request and response
processing using a gRPC-based service callout in Go. It combines both **header**
and **body** mutations across the full request/response lifecycle.

Use this callout when you need a **reference implementation** or want to combine
multiple transformation patterns in a single service.

---

## How It Works

1. Request headers are intercepted and modified.
2. Request body is replaced before reaching the backend.
3. Response headers are modified before returning to the client.
4. Response body is replaced before final delivery.

---

## Callbacks / Handlers

| Handler | Behavior |
|---|---|
| `HandleRequestHeaders` | Adds `header-request: Value-request`. |
| `HandleResponseHeaders` | Adds `header-response: Value-response`. |
| `HandleRequestBody` | Replaces body with `new-body-request`. |
| `HandleResponseBody` | Replaces body with `new-body-response`. |

---

## Run

**Go:**

```bash
cd callouts/go
EXAMPLE_TYPE=basic_callout_server go run ./extproc/cmd/example/main.go
```

---

## Test

```bash
cd callouts/go
go test ./extproc/examples/basic_callout_server/...
```

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request mutation** | Headers and body are modified before backend. |
| **Response mutation** | Headers and body are modified before client. |
| **Full lifecycle** | Demonstrates end-to-end transformation. |

---

## Available Languages

- [x] [Go](.) (this directory)
- [ ] Python
- [ ] Java