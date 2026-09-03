# Add Header Callout

This callout server adds custom headers to both HTTP requests and responses as
they pass through the load balancer. It demonstrates the core header mutation
pattern — adding headers, removing headers, and controlling the route cache. It
overrides `on_request_headers` and `on_response_headers` to apply different
mutations on each path. Use this callout when you need to inject metadata,
routing signals, or tracking headers into traffic flowing through your load
balancer.

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `on_request_headers` callback adds a `header-request: request`
   header and clears the route cache (forcing the load balancer to re-evaluate
   routing with the new headers).
3. When the origin server responds, the load balancer sends a second
   `ProcessingRequest` with `response_headers`.
4. The server's `on_response_headers` callback adds a
   `header-response: response` header and removes any existing `foo` header.
5. The modified response is returned to the client.

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Adds `header-request: request`, clears route cache |
| `on_response_headers` | Adds `header-response: response`, removes the `foo` header |


## Run

```bash
cd callouts/python
python -m extproc.example.add_header.service_callout_example
```

## Test

```bash
cd callouts/python
pytest extproc/tests/basic_grpc_test.py
```

The `add_header` example is tested as part of the basic gRPC integration tests
rather than having a dedicated test file.


## Expected Behavior

| Scenario | Description |
|---|---|
| **Request header addition** | For any incoming HTTP request, the system injects the header-request: request field and clears the route cache to ensure fresh processing. |
| **Response header addition** | For any HTTP response received from the origin, the system appends the header-response: response field to the response headers |
| **Response header removal** | When a response contains a foo header, the system identifies and strips that specific header before final delivery. |
| **No `foo` header present** | If the foo header is missing from the response, the system performs a "no-op," meaning it continues processing without error or modification. |

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/add_header/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/AddHeader.java)
