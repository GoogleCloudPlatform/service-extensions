# Set Cookie Callout

This callout server conditionally sets a cookie on HTTP responses based on the
presence of a specific request header. It demonstrates how to modify response
headers and inject cookies dynamically in a Layer 7 load balancer.

The server checks for the presence of the `cookie-check` header and, if found,
adds a `Set-Cookie` header to the response. If the header is not present, no
modification is applied.

Use this callout when you need **conditional cookie injection**, **client
targeting**, or **response header enrichment** without modifying backend services.

---

## How It Works

1. The load balancer forwards a request to the backend service.
2. When the backend responds, the load balancer sends a `ProcessingRequest`
   with `response_headers` to the callout server.
3. The server checks for the presence of the `cookie-check` header.
4. If the header exists:
   - A `Set-Cookie` header is added to the response.
5. If the header is not present:
   - No mutation is applied and the response continues unchanged.
6. The modified (or original) response is returned to the client.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_response_headers` | Checks for `cookie-check` header and conditionally adds a `Set-Cookie` header to the response. |

---

## Run

```bash
cd callouts/python
python -m extproc.example.set_cookie.service_callout_example
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
| **Header present (`cookie-check`)** | Response includes `Set-Cookie: your_cookie_name=cookie_value; Max-Age=3600; Path=/`. |
| **Header missing** | No cookie is added; response passes through unchanged. |
| **Conditional mutation** | Cookie is only set for requests that include the required header. |
| **Response enrichment** | Enables dynamic cookie injection without backend changes. |

---

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/set_cookie/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/SetCookie.java)