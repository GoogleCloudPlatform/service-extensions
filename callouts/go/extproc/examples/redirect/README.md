# Redirect Callout (Go)

This callout server performs an HTTP redirect for incoming requests using an
immediate response. It demonstrates how to short-circuit normal request
processing in a Layer 7 load balancer and return a redirect response directly
to the client.

The server intercepts request headers and responds with a `301 Moved Permanently`
status, instructing the client to navigate to a different URL via the `Location`
header.

Use this callout when you need **URL redirection**, **traffic migration**, or
**request short-circuiting** without forwarding the request to a backend service.

---

## How It Works

1. Intercepts request headers.
2. Returns an immediate response:
   - Status: `301 Moved Permanently`
   - Header: `Location: http://service-extensions.com/redirect`
3. Request is never forwarded to backend.

---


## Callbacks / Handlers

| Handler | Behavior |
|---|---|
| `HandleRequestHeaders` | Returns immediate 301 redirect response. |

---

## Run

```bash
cd callouts/go
EXAMPLE_TYPE=redirect go run ./extproc/cmd/example/main.go
```

---

## Test

```bash
cd callouts/go
go test ./extproc/examples/redirect/...
```

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Any incoming request** | The request is not forwarded to a backend. |
| **Redirect response** | The client receives a `301 Moved Permanently` response. |
| **Location header** | The response includes `Location: http://service-extensions.com/redirect`. |
| **Immediate response** | Processing is short-circuited and handled entirely by the callout. |

---

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/redirect/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/Redirect.java)