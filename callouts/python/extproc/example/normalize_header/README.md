# Header Normalization Plugin (Python)

This plugin implements device-type detection at the proxy layer by inspecting the `:authority` pseudo-header of every incoming request and injecting a `client-device-type` header that classifies the request as `mobile`, `tablet`, or `desktop`. Downstream services can use this header to shard or route traffic without needing to replicate the detection logic themselves. Use this plugin when you need to normalise request context based on the host value and propagate a device classification to upstream services transparently. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler delegates to `add_device_type_header`, which iterates over the incoming headers looking for the `:authority` pseudo-header and decodes its raw value as UTF-8.
3. If the `:authority` header is found, `get_device_type` classifies it: values containing `"m.example.com"` return `"mobile"`, values containing `"t.example.com"` return `"tablet"`, and all other values return `"desktop"`.
4. The resolved device type is injected as the header `client-device-type: <device_type>` and the route cache is cleared to force Envoy to recompute its routing decision based on the new header.
5. If no `:authority` header is found, an empty `HeadersResponse` is returned and no mutation is applied.
6. The modified request is forwarded to the upstream service.

## Implementation Notes

- **Class structure**: `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the request headers callback. The core logic is extracted into the `add_device_type_header` helper method, keeping the callback itself a single-line delegation. No other phases are registered, so all other HTTP lifecycle phases pass through unmodified.
- **Device type classification**: `get_device_type(host_value)` is a module-level function that applies substring matching in priority order: `"m.example.com"` is checked first for mobile, then `"t.example.com"` for tablet, with `"desktop"` as the unconditional fallback. The function operates on the full host string, so subdomains like `"m.example.com/path"` are matched correctly.
- **Authority header extraction**: `add_device_type_header` uses a generator expression with `next(..., None)` to find the first header whose `key == ':authority'` and decode its `raw_value` as UTF-8. The `None` default means a missing `:authority` header is handled gracefully — the method returns an empty `service_pb2.HeadersResponse()` without applying any mutation.
- **Header mutation**: When a host value is found, `callout_tools.add_header_mutation` is called with `add=[('client-device-type', device_type)]` and `clear_route_cache=True`. Clearing the route cache ensures Envoy re-evaluates any routing rules that may depend on the newly injected `client-device-type` header.
- **Server startup**: The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required for the default setup. The host substrings used for device classification and the injected header name are hardcoded in the plugin:
- `mobile host pattern`: `"m.example.com"`
- `tablet host pattern`: `"t.example.com"`
- `default device type`: `"desktop"`
- `injected header`: `client-device-type`
- `request phase route cache`: cleared (`True`)

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.normalize_header
```

Or run directly:
```bash
python normalize_header.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the normalize_header sample
python -m pytest tests/normalize_header_test.py

# With verbose output
python -m pytest -v tests/normalize_header_test.py
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Mobile host detected** | A request with `:authority: m.example.com` gets `client-device-type: mobile` injected and the route cache cleared. |
| **Tablet host detected** | A request with `:authority: t.example.com` gets `client-device-type: tablet` injected and the route cache cleared. |
| **Desktop host (default)** | A request with any other `:authority` value (e.g. `www.example.com`) gets `client-device-type: desktop` injected and the route cache cleared. |
| **No `:authority` header** | A request without the `:authority` pseudo-header returns an empty `HeadersResponse` with no mutation applied. |
| **Response phases** | All response phases pass through unmodified; no response callbacks are registered. |

## Available Languages

- [x] [Python](normalize_header.py)
