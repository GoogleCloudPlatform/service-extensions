# Basic Callout Server Plugin (Python)

This plugin demonstrates a complete ext_proc callout service by handling all four HTTP processing phases simultaneously: request headers, response headers, request body, and response body. Each phase supports three distinct behaviours: denying the connection on a forbidden signal, returning a mock response on a mock signal, and applying a standard mutation otherwise. Use this plugin as a reference implementation or starting point when you need a full-featured callout service that intercepts every phase of the HTTP lifecycle with conditional logic. It operates during the **request headers**, **response headers**, **request body**, and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. If the request contains a header named `bad-header`, the connection is denied and closed immediately.
3. If the request contains a header named `mock`, a mock response with `Mock-Response: Mocked-Value` is returned instead of the standard mutation.
4. Otherwise, the header `header-request: request` is added, the `foo` header is removed, and the route cache is cleared.
5. The proxy then invokes `on_request_body`.
6. If the body contains the substring `bad-body`, the connection is denied. If it contains `mock`, a mock body of `"Mocked-Body"` is returned. Otherwise, the body is replaced with `"replaced-body"`.
7. The modified request is forwarded to the upstream service.
8. When the upstream responds, the proxy invokes `on_response_headers`.
9. The same deny and mock checks are applied. Otherwise, the header `header-response: response` is added.
10. The proxy then invokes `on_response_body`.
11. The same deny and mock checks are applied. Otherwise, the body is cleared (no explicit replacement value passed).
12. The fully modified response is returned to the client.

## Implementation Notes

- **Class structure**: `CalloutServerExample` extends `callout_server.CalloutServer` and overrides all four processing callbacks. No constructor override is needed; the base class handles server lifecycle. The server is started by calling `.run()` directly on an instance.
- **Deny logic**: All four callbacks call `callout_tools.deny_callout(context)` as the first check, using `callout_tools.headers_contain` or `callout_tools.body_contains` to inspect the incoming data. Denial closes the gRPC connection immediately, preventing any further processing or upstream forwarding.
- **Mock responses**: `generate_mock_header_response` returns `callout_tools.add_header_mutation([("Mock-Response", "Mocked-Value")])` and `generate_mock_body_response` returns `callout_tools.add_body_mutation("Mocked-Body")`. These are returned early when the `mock` signal is detected, bypassing the standard mutation path entirely.
- **Request header mutation**: The standard path calls `callout_tools.add_header_mutation` with `add=[('header-request', 'request')]`, `remove=['foo']`, and `clear_route_cache=True`, injecting a new header, stripping `foo`, and forcing Envoy to recompute its routing decision.
- **Response header mutation**: The standard path calls `callout_tools.add_header_mutation` with only `add=[('header-response', 'response')]`, preserving all existing response headers and leaving the route cache intact.
- **Request body mutation**: The standard path calls `callout_tools.add_body_mutation(body='replaced-body')`, replacing the incoming request body with the static string `"replaced-body"`.
- **Response body mutation**: The standard path calls `callout_tools.add_body_mutation()` with no arguments, which clears the response body without substituting new content.
- **Server startup**: The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required for the default setup. All signal strings, injected header names and values, and body replacement strings are hardcoded in the callbacks:
- `deny signal (headers)`: `bad-header`
- `deny signal (body)`: `bad-body`
- `mock signal (headers and body)`: `mock`
- `mock header added`: `Mock-Response: Mocked-Value`
- `mock body replacement`: `"Mocked-Body"`
- `request header added`: `header-request: request`
- `request header removed`: `foo`
- `request route cache`: cleared (`True`)
- `response header added`: `header-response: response`
- `request body replacement`: `"replaced-body"`
- `response body`: cleared (no replacement)

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.basic_callout_server
```

Or run directly:
```bash
python basic_callout_server.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the basic callout server
python -m pytest tests/basic_callout_server_test.py

# With verbose output
python -m pytest -v tests/basic_callout_server_test.py
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request header injected** | Any request without `bad-header` or `mock` gets `header-request: request` added, `foo` removed, and the route cache cleared. |
| **Request header denied** | A request containing `bad-header` has the connection denied and closed immediately. |
| **Request header mocked** | A request containing `mock` returns `Mock-Response: Mocked-Value` instead of the standard mutation. |
| **Response header injected** | Any response without `bad-header` or `mock` gets `header-response: response` added. |
| **Response header denied** | A response containing `bad-header` has the connection denied and closed immediately. |
| **Response header mocked** | A response containing `mock` returns `Mock-Response: Mocked-Value` instead of the standard mutation. |
| **Request body replaced** | A body without `bad-body` or `mock` is replaced with `"replaced-body"`. |
| **Request body denied** | A body containing `bad-body` has the connection denied and closed immediately. |
| **Request body mocked** | A body containing `mock` is replaced with `"Mocked-Body"`. |
| **Response body cleared** | A body without `bad-body` or `mock` is cleared with no replacement. |
| **Response body denied** | A body containing `bad-body` has the connection denied and closed immediately. |
| **Response body mocked** | A body containing `mock` is replaced with `"Mocked-Body"`. |

## Available Languages

- [x] [Python](basic_callout_server.py)
