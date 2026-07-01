# Redirect Callout

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

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `on_request_headers` callback is triggered.
3. Instead of forwarding the request, the server returns an `ImmediateResponse`.
4. The response includes:
   - HTTP status code `301 (Moved Permanently)`
   - A `Location` header pointing to the redirect target
5. The load balancer immediately returns this response to the client, bypassing
   any backend service.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Returns an immediate 301 redirect response with a `Location` header. |

---

## Run

```bash
cd callouts/python
python -m extproc.example.redirect.service_callout_example
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
| **Any incoming request** | The request is not forwarded to a backend. |
| **Redirect response** | The client receives a `301 Moved Permanently` response. |
| **Location header** | The response includes `Location: http://service-extensions.com/redirect`. |
| **Immediate response** | Processing is short-circuited and handled entirely by the callout. |

---

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/redirect/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/Redirect.java)