# Add Body Callout

This callout server modifies HTTP request and response bodies as they pass
through the load balancer. It demonstrates the core body mutation pattern —
appending content to a request body and replacing a response body entirely. It
overrides `on_request_body` and `on_response_body` to apply different mutations
on each path. Use this callout when you need to enrich, transform, or replace
body content flowing through your load balancer.

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_body` to the callout server.
2. The server's `on_request_body` callback reads the existing body, appends
   `-added-request-body` to it, and returns the mutation to the load balancer.
3. When the origin server responds, the load balancer sends a second
   `ProcessingRequest` with `response_body`.
4. The server's `on_response_body` callback replaces the entire body with the
   string `new-body`.
5. The modified response is returned to the client.

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_body` | Appends `-added-request-body` to the existing request body |
| `on_response_body` | Replaces the response body entirely with `new-body` |

## Run

**Python:**

```bash
cd callouts/python
python -m extproc.example.add_body.service_callout_example
```

**Go:**

```bash
cd callouts/go
EXAMPLE_TYPE=add_body go run ./extproc/cmd/example/main.go
```

**Java:**

```bash
cd callouts/java/service-callout
./gradlew run -PmainClass=example.AddBody
```

## Test

```bash
cd callouts/python
pytest extproc/tests/basic_grpc_test.py
```

The `add_body` example is tested as part of the basic gRPC integration tests
rather than having a dedicated test file.


## Expected Behavior

| Scenario | Description |
|---|---|
| **Request body mutation** | For any incoming HTTP request, the system reads the existing body and appends `-added-request-body` to it before forwarding to the origin. |
| **Response body replacement** | For any HTTP response received from the origin, the system discards the original body and replaces it with the static string `new-body`. |
| **Empty request body** | If the request body is empty, the mutation appends `-added-request-body` to an empty string, resulting in the body containing only `-added-request-body`. |
| **No body present** | If no body is present in the response, the replacement still applies, and the client receives `new-body` as the response payload. |

## Available Languages

- [x] [Python](.) (this directory)
- [ ] Go
- [ ] Java
