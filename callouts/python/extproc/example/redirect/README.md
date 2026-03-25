# Redirect Plugin (Python)

This plugin implements an unconditional HTTP redirect at the proxy layer by intercepting every incoming request and immediately returning a `301 Moved Permanently` response with a hardcoded `Location` header, before the request ever reaches the upstream service. Use this plugin when you need to enforce a blanket redirect for all traffic through a proxy — such as domain migrations, protocol enforcement, or legacy endpoint retirement — without involving any backend logic. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler unconditionally calls `callout_tools.header_immediate_response` with status code `301` and a `Location: http://service-extensions.com/redirect` header.
3. An `ImmediateResponse` is returned, instructing Envoy to short-circuit the request and send the redirect directly to the client.
4. The upstream service is never contacted.

## Implementation Notes

- **Class structure**: `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the request headers callback. No other phases are registered, so all other HTTP lifecycle phases would pass through unmodified — though in practice no request ever reaches them since every request is short-circuited at this phase.
- **Immediate response**: `on_request_headers` returns the result of `callout_tools.header_immediate_response(code=301, headers=[('Location', 'http://service-extensions.com/redirect')])`. Unlike a normal header mutation response, an `ImmediateResponse` instructs Envoy to stop processing the request and reply to the client directly, bypassing the upstream entirely.
- **Unconditional behaviour**: The handler performs no inspection of the incoming request. Every request — regardless of path, method, or headers — receives the same redirect response.
- **`header_immediate_response` utility**: The callback delegates to `callout_tools.header_immediate_response`, a shared helper from the `extproc.service` package that constructs the appropriate `ImmediateResponse` protobuf message with the given status code and headers, abstracting away the boilerplate of building the response directly.
- **Server startup**: The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required. The redirect target and status code are hardcoded directly in the callback:
- `HTTP status code`: `301` (Moved Permanently)
- `redirect target`: `http://service-extensions.com/redirect`
- `response body`: none
- `response trailers`: none

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

| Scenario | Description |
|---|---|
| **Any request is redirected** | Every HTTP request, regardless of path or method, receives a `301 Moved Permanently` with `Location: http://service-extensions.com/redirect`. |
| **Upstream is never reached** | The request is short-circuited at the proxy on every call; no upstream connection is made. |
| **No body in response** | The immediate response is returned with no body content. |
| **Response phases** | Never reached; all requests are terminated at the request headers phase. |

## Available Languages

- [x] [Python](redirect.py)
