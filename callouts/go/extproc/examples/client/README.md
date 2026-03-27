# Client Callout (Go)

This callout server provides a full example of request and response processing,
including both headers and bodies. It behaves identically to the basic callout
server and is typically used for **client-side testing or demonstrations**.

---

## How It Works

1. Modifies request headers and body.
2. Modifies response headers and body.
3. Returns fully transformed traffic.

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

```bash
cd callouts/go
EXAMPLE_TYPE=client go run ./extproc/cmd/example/main.go
```

---

## Test

```bash
cd callouts/go
go test ./extproc/examples/client/...
```

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Full mutation** | Both headers and bodies are transformed. |
| **Testing use case** | Useful for validating client-callout flows. |

---

## Available Languages

- [x] [Go](.) (this directory)
- [ ] Python
- [ ] Java