# Set Cookie Plugin (Python)

This plugin implements conditional cookie injection at the proxy layer by inspecting outgoing response headers for the presence of a `cookie-check` header and, when found, appending a `Set-Cookie` header to the response. This allows the proxy to selectively set cookies for specific clients without modifying upstream application logic. Use this plugin when you need to inject session cookies, tracking cookies, or feature flags at the proxy layer based on a client-supplied signal. It operates during the **response headers** processing phase.

## How It Works

1. The proxy receives a response from the upstream service and invokes the plugin's `on_response_headers` callback.
2. The handler calls `validate_header` to check whether the response headers contain a header named `cookie-check`.
3. If the `cookie-check` header is present, its raw value is returned as truthy and `Set-Cookie: your_cookie_name=cookie_value; Max-Age=3600; Path=/` is injected into the response headers.
4. If the `cookie-check` header is absent, `validate_header` returns `None`, no mutation is applied, and the response passes through unmodified.
5. The modified response is returned to the client.

## Implementation Notes

- **Class structure**: `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the response headers callback. No request-phase callbacks are registered, so all request phases pass through unmodified. The server is started by calling `.run()` directly on an instance.
- **Header validation**: `validate_header` is a module-level function that uses a generator expression with `next(..., None)` to iterate over `http_headers.headers.headers`, matching on `header.key == 'cookie-check'` and returning `header.raw_value` (the raw bytes) if found. Returning the raw value rather than a boolean means the caller receives both the truthiness signal and the header value in a single call, though the value itself is not used in the current mutation logic.
- **Cookie injection**: When `validate_header` returns a truthy result, `callout_tools.add_header_mutation` is called with `add=[('Set-Cookie', 'your_cookie_name=cookie_value; Max-Age=3600; Path=/')]`. No headers are removed and no `clear_route_cache` argument is passed, preserving all existing response headers and leaving the route cache intact.
- **No-op on missing header**: If `validate_header` returns `None`, `on_response_headers` returns `None` implicitly. The base `CalloutServer` treats a `None` return as a no-op, allowing the response to pass through without any mutation.
- **Server startup**: The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required for the default setup. The trigger header name, cookie name, and cookie attributes are hardcoded in the plugin:
- `trigger header`: `cookie-check` (presence checked; value not inspected)
- `cookie injected`: `your_cookie_name=cookie_value`
- `cookie Max-Age`: `3600` seconds
- `cookie Path`: `/`

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.set_cookie
```

Or run directly:
```bash
python set_cookie.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the set_cookie sample
python -m pytest tests/set_cookie_test.py

# With verbose output
python -m pytest -v tests/set_cookie_test.py
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Cookie injected** | A response containing the `cookie-check` header gets `Set-Cookie: your_cookie_name=cookie_value; Max-Age=3600; Path=/` added to its headers. |
| **No mutation applied** | A response without the `cookie-check` header passes through unmodified; no headers are added or removed. |
| **Request phases** | All request phases pass through unmodified; no request callbacks are registered. |

## Available Languages

- [x] [Python](set_cookie.py)