# Add Custom Response Callout

This callout server applies conditional mutations to both HTTP headers and
bodies as they pass through the load balancer. It demonstrates advanced traffic
control patterns — mock responses, body replacement, header injection, and
connection denial. It overrides all four core callbacks (`on_request_headers`,
`on_response_headers`, `on_request_body`, and `on_response_body`) to evaluate
each request and response against a set of rules before deciding which mutation
to apply. Use this callout when you need fine-grained control over traffic
based on the content of headers or bodies, including short-circuiting requests
with mock responses or blocking malicious traffic entirely.

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `on_request_headers` callback inspects the headers: if
   `bad-header` is present, the connection is denied; if a `mock` header is
   found, a mock response with `Mock-Response: Mocked-Value` is returned;
   otherwise, `header-request: request` is added and the route cache is
   cleared.
3. The load balancer then sends a `ProcessingRequest` with `request_body`.
4. The server's `on_request_body` callback inspects the body: if it contains
   `bad-body`, the connection is denied; if it contains `mock`, a mock body
   of `Mocked-Body` is returned; otherwise, the body is replaced with
   `replaced-body`.
5. When the origin server responds, the load balancer sends a
   `ProcessingRequest` with `response_headers`.
6. The server's `on_response_headers` callback applies the same deny/mock
   logic, and otherwise injects the `header-response: response` header.
7. The load balancer sends a final `ProcessingRequest` with `response_body`.
8. The server's `on_response_body` callback applies the same deny/mock logic,
   and otherwise clears the body.
9. The fully modified response is returned to the client.

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Denies on `bad-header`; returns mock on `mock`; otherwise adds `header-request: request` and clears route cache |
| `on_response_headers` | Denies on `bad-header`; returns mock on `mock`; otherwise adds `header-response: response` |
| `on_request_body` | Denies on `bad-body`; returns mock body on `mock`; otherwise replaces body with `replaced-body` |
| `on_response_body` | Denies on `bad-body`; returns mock body on `mock`; otherwise clears the body |

## Run

```bash
cd callouts/python
python -m extproc.example.add_custom_response.service_callout_example
```

## Test

```bash
cd callouts/python
pytest extproc/tests/basic_grpc_test.py
```

The `add_custom_response` example is tested as part of the basic gRPC
integration tests rather than having a dedicated test file.


## Expected Behavior

| Scenario | Description |
|---|---|
| **Bad header detected** | If any request or response contains the `bad-header` header, the server immediately denies the callout and closes the connection. |
| **Mock header detected** | If any request or response contains the `mock` header, the server short-circuits normal processing and returns a `Mock-Response: Mocked-Value` header mutation. |
| **Standard request header flow** | For normal requests with no special headers, the server injects `header-request: request`, removes `foo`, and clears the route cache. |
| **Standard response header flow** | For normal responses with no special headers, the server injects `header-response: response` into the response headers. |
| **Bad body detected** | If a request or response body contains the substring `bad-body`, the server immediately denies the callout and closes the connection. |
| **Mock body detected** | If a request or response body contains the substring `mock`, the server short-circuits normal processing and returns a body mutation with `Mocked-Body`. |
| **Standard request body flow** | For normal request bodies with no special substrings, the server replaces the body with `replaced-body`. |
| **Standard response body flow** | For normal response bodies with no special substrings, the server clears the body content. |

## Available Languages

- [x] [Python](.) (this directory)
- [ ] Go
- [ ] Java
