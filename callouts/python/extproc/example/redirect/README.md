# Redirect Plugin (Python)

This plugin implements an unconditional HTTP redirect at the proxy layer by intercepting every incoming request and immediately returning a `301 Moved Permanently` response with a hardcoded `Location` header, before the request ever reaches the upstream service. Use this plugin when you need to enforce a blanket redirect for all traffic through a proxy — such as domain migrations, protocol enforcement, or legacy endpoint retirement — without involving any backend logic. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler unconditionally calls `callout_tools.header_immediate_response` with status code `301` and a `Location: http://service-extensions.com/redirect` header.
3. An `ImmediateResponse` is returned, instructing Envoy to short-circuit the request and send the redirect directly to the client.
4. The upstream service is never contacted.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_headers` | Intercepts every incoming HTTP request and returns an immediate `301` redirect response with a `Location` header |

## Key Code Walkthrough

- **Class structure** — `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the request headers callback. No other phases are registered, so all other HTTP lifecycle phases would pass through unmodified — though in practice no request ever reaches them since every request is short-circuited at this phase.

- **Immediate response** — `on_request_headers` returns the result of `callout_tools.header_immediate_response(code=301, headers=[('Location', 'http://service-extensions.com/redirect')])`. Unlike a normal header mutation response, an `ImmediateResponse` instructs Envoy to stop processing the request and reply to the client directly, bypassing the upstream entirely.

- **Unconditional behaviour** — The handler performs no inspection of the incoming request. Every request — regardless of path, method, or headers — receives the same redirect response.

- **`header_immediate_response` utility** — The callback delegates to `callout_tools.header_immediate_response`, a shared helper from the `extproc.service` package that constructs the appropriate `ImmediateResponse` protobuf message with the given status code and headers, abstracting away the boilerplate of building the response directly.

- **Server startup** — The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required. The redirect target and status code are hardcoded directly in the callback:

- HTTP status code: `301` (Moved Permanently)
- Redirect target: `http://service-extensions.com/redirect`
- Response body: none
- Response trailers: none

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.redirect
```

Or run directly:
```bash
python redirect.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the redirect sample
python -m pytest tests/redirect_test.py

# With verbose output
python -m pytest -v tests/redirect_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Any request is redirected** | Any HTTP request regardless of path or method | `301 Moved Permanently` with `Location: http://service-extensions.com/redirect` |
| **Upstream is never reached** | Any HTTP request | Request short-circuited at the proxy; no upstream connection made |
| **No body in response** | Any HTTP request | Immediate response returned with no body content |
| **Response phases** | Any HTTP response | Never reached; all requests are terminated at the request headers phase |

## Available Languages

- [x] [Python](redirect.py)