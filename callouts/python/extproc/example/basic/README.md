# Basic Callout Server Plugin (Python)

This plugin demonstrates a complete ext_proc callout service by handling all four HTTP processing phases simultaneously: request headers, response headers, request body, and response body. It rewrites pseudo-headers and injects custom headers into the request, adds a header to the response, replaces the request body with a static string, and clears the response body entirely. Use this plugin as a comprehensive reference implementation when you need a full-featured callout service that intercepts every phase of the HTTP lifecycle. It operates during the **request headers**, **response headers**, **request body**, and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler rewrites the `:authority` header to `"service-extensions.com"` and the `:path` header to `"/"`, adds `header-request: request`, removes the `foo` header, and clears the route cache to force Envoy to recompute its routing decision.
3. The proxy then invokes `on_request_body`, which replaces the incoming request body with the static string `"replaced-body"`.
4. The modified request is forwarded to the upstream service.
5. When the upstream responds, the proxy invokes `on_response_headers`, which adds the header `hello: service-extensions` to the outgoing response headers.
6. The proxy then invokes `on_response_body`, which clears the response body entirely without substituting any new content.
7. The fully modified response is returned to the client.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_headers` | Rewrites `:authority` and `:path`; adds `header-request: request`; removes `foo`; clears route cache |
| `on_response_headers` | Adds `hello: service-extensions` to response headers |
| `on_request_body` | Replaces the request body with `"replaced-body"` |
| `on_response_body` | Clears the response body entirely |

## Key Code Walkthrough

- **Class structure** — `BasicCalloutServer` extends `CalloutServer` and overrides all four processing callbacks. The `context` argument is unused in every callback and is therefore named `_` throughout, keeping the signatures clean. The server accepts command-line arguments at startup via `add_command_line_args()`.

- **Request header mutation** — `on_request_headers` calls `add_header_mutation` with three entries in the `add` list: `(':authority', 'service-extensions.com')` and `(':path', '/')` to rewrite Envoy pseudo-headers, and `('header-request', 'request')` to inject a custom header. The `remove=['foo']` argument strips the `foo` header, and `clear_route_cache=True` forces Envoy to discard its previously computed route. Each incoming callout is logged at `DEBUG` level before processing.

- **Response header mutation** — `on_response_headers` calls `add_header_mutation` with only `add=[('hello', 'service-extensions')]`, preserving all existing response headers and leaving the route cache intact.

- **Request body mutation** — `on_request_body` calls `add_body_mutation(body='replaced-body')`, substituting the incoming request body with the static string `"replaced-body"`.

- **Response body mutation** — `on_response_body` calls `add_body_mutation(clear_body=True)`, removing the response body entirely without providing a replacement string. This is distinct from replacing the body with an empty string — `clear_body=True` instructs Envoy to drop the body at the proxy layer.

- **Command-line arguments** — The `__main__` block uses `add_command_line_args().parse_args()` to parse startup flags and passes them as keyword arguments to `BasicCalloutServer(**vars(args))`, allowing server address, port, and TLS settings to be configured at runtime without code changes.

- **Logging** — Every callback logs the received callout at `DEBUG` level before applying any mutation, making it straightforward to trace the exact headers and body values seen by the proxy during development and testing.

## Configuration

Runtime configuration is provided via command-line arguments parsed by `add_command_line_args()`. All mutation values are hardcoded in the callbacks:

- `:authority` rewritten to: `service-extensions.com`
- `:path` rewritten to: `/`
- Request header added: `header-request: request`
- Request header removed: `foo`
- Request phase route cache: cleared (`True`)
- Response header added: `hello: service-extensions`
- Request body replacement: `"replaced-body"`
- Response body: cleared (`clear_body=True`)

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

Or run directly, optionally passing command-line arguments:
```bash
# Default configuration
python basic_callout_server.py

# Custom address and port
python basic_callout_server.py --address 0.0.0.0 --port 8443
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the basic_callout_server sample
python -m pytest tests/basic_callout_server_test.py

# With verbose output
python -m pytest -v tests/basic_callout_server_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Pseudo-headers rewritten** | Any HTTP request | `:authority` set to `service-extensions.com`; `:path` set to `/` |
| **Request header injected** | Any HTTP request | `header-request: request` added to request headers |
| **Request header removed** | Request containing `foo` header | `foo` header stripped from request |
| **Request route cache cleared** | Any HTTP request | Envoy recomputes routing after request header mutation |
| **Response header injected** | Any HTTP response | `hello: service-extensions` added to response headers |
| **Request body replaced** | Any HTTP request body | Body replaced with `"replaced-body"` |
| **Response body cleared** | Any HTTP response body | Response body dropped entirely at the proxy layer |

## Available Languages

- [x] [Python](basic_callout_server.py)
- [x] [Go](add_header.go)
- [x] [Java](AddHeader.java)
