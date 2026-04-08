# Basic Callout

This callout server provides a non-comprehensive reference implementation
covering all four core callback types — request headers, response headers,
request body, and response body. It demonstrates the most common mutation
patterns in a single server: rewriting pseudo-headers, injecting custom
headers, removing headers, clearing the route cache, replacing a request body,
and clearing a response body. It overrides all four callbacks to apply a
distinct mutation on each path. Use this callout as a starting point or
reference when building a new callout server from scratch.

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `on_request_headers` callback rewrites the `:authority` header
   to `service-extensions.com` and the `:path` header to `/`, adds the header
   `header-request: request`, removes any existing `foo` header, and clears the
   route cache.
3. The load balancer then sends a `ProcessingRequest` with `request_body`.
4. The server's `on_request_body` callback replaces the entire request body
   with the string `replaced-body`.
5. When the origin server responds, the load balancer sends a
   `ProcessingRequest` with `response_headers`.
6. The server's `on_response_headers` callback injects the header
   `hello: service-extensions` into the response.
7. The load balancer sends a final `ProcessingRequest` with `response_body`.
8. The server's `on_response_body` callback clears the response body entirely.
9. The modified response is returned to the client.

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Rewrites `:authority` to `service-extensions.com` and `:path` to `/`, adds `header-request: request`, removes `foo`, clears route cache |
| `on_response_headers` | Adds `hello: service-extensions` |
| `on_request_body` | Replaces the request body with `replaced-body` |
| `on_response_body` | Clears the response body |

## Run

**Python:**

```bash
cd callouts/python
python -m extproc.example.basic_callout.service_callout_example
```

**Go:**

```bash
cd callouts/go
EXAMPLE_TYPE=basic_callout go run ./extproc/cmd/example/main.go
```

**Java:**

```bash
cd callouts/java/service-callout
./gradlew run -PmainClass=example.BasicCallout
```

## Test

```bash
cd callouts/python
pytest extproc/tests/basic_grpc_test.py
```

The `basic_callout` example is tested as part of the basic gRPC integration
tests rather than having a dedicated test file.


## Expected Behavior

| Scenario | Description |
|---|---|
| **Authority and path rewrite** | For any incoming HTTP request, the system rewrites the `:authority` header to `service-extensions.com` and the `:path` header to `/` before forwarding to the origin. |
| **Request header injection** | The system adds the `header-request: request` header to every incoming request. |
| **Request header removal** | When a request contains a `foo` header, the system strips it before forwarding. If the `foo` header is absent, processing continues without modification. |
| **Route cache cleared** | After mutating request headers, the route cache is always cleared so the load balancer re-evaluates routing with the updated headers. |
| **Response header injection** | For any HTTP response received from the origin, the system appends the `hello: service-extensions` header before delivery to the client. |
| **Request body replacement** | For any incoming request body, the system discards the original content and replaces it with the static string `replaced-body`. |
| **Response body cleared** | For any HTTP response received from the origin, the system clears the body entirely before delivery to the client. |

## Available Languages

- [x] [Python](.) (this directory)
- [ ] Go
- [ ] Java
