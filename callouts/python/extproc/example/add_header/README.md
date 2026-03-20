# Add Header Plugin (Python)

This plugin demonstrates HTTP header manipulation at the proxy layer by intercepting both incoming request headers and outgoing response headers. It adds a new header to each phase, removes a specific header from the response, and controls route cache invalidation independently per phase. Use this plugin when you need to inject metadata headers into requests, enrich or sanitise response headers, or force Envoy to recompute its routing decision after a header mutation. It operates during the **request headers** and **response headers** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler adds the header `header-request: request` to the incoming request headers and sets `clear_route_cache=True`, instructing Envoy to recompute the routing decision after the mutation.
3. The modified request is forwarded to the upstream service.
4. When the upstream responds, the proxy invokes the plugin's `on_response_headers` callback.
5. The handler adds the header `header-response: response` to the outgoing response headers and simultaneously removes the `foo` header. The route cache is left intact (no `clear_route_cache` argument).
6. The modified response is returned to the client.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_headers` | Adds `header-request: request` to request headers; clears the route cache |
| `on_response_headers` | Adds `header-response: response` to response headers; removes `foo` |

## Key Code Walkthrough

- **Class structure** — `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the two header phase callbacks. No constructor override is needed; the base class handles all server lifecycle concerns. The server is started by calling `.run()` directly on an instance.

- **Request header mutation** — `on_request_headers` calls `callout_tools.add_header_mutation` with `add=[('header-request', 'request')]` and `clear_route_cache=True`. No `remove` argument is passed, so no existing headers are stripped. Setting `clear_route_cache=True` tells Envoy to discard any previously computed route and re-evaluate routing based on the mutated headers.

- **Response header mutation** — `on_response_headers` calls `callout_tools.add_header_mutation` with `add=[('header-response', 'response')]` and `remove=['foo']`. No `clear_route_cache` argument is passed, so it defaults to `False`, preserving the route cache — appropriate for the response phase where routing decisions are already finalised.

- **`add_header_mutation` utility** — Both callbacks delegate to `callout_tools.add_header_mutation`, a shared helper from the `extproc.service` package that constructs the appropriate `HeadersResponse` protobuf message, abstracting away the boilerplate of building the header mutation directly.

- **Server startup** — The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required for the default setup. All header names, values, and cache settings are hardcoded directly in each callback:

- Request header added: `header-request: request`
- Request phase route cache: cleared (`True`)
- Response header added: `header-response: response`
- Response header removed: `foo`
- Response phase route cache: preserved (default `False`)

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.add_header
```

Or run directly:
```bash
python add_header.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the add_header sample
python -m pytest tests/add_header_test.py

# With verbose output
python -m pytest -v tests/add_header_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request header injected** | Any HTTP request | `header-request: request` added to request headers |
| **Request route cache cleared** | Any HTTP request | Envoy recomputes routing after request header mutation |
| **Response header injected** | Any HTTP response | `header-response: response` added to response headers |
| **Response header removed** | Response containing `foo` header | `foo` header stripped from response |
| **Response route cache preserved** | Any HTTP response | Envoy routing decision unchanged after response header mutation |

## Available Languages

- [x] [Go](add_header.go)
- [x] [Java](AddHeader.java)
- [x] [Python](service_callout_example.py)