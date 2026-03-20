# Update Header Plugin (Python)

This plugin demonstrates deterministic header overwriting at the proxy layer by intercepting both incoming request headers and outgoing response headers and updating a specific header in each phase using the `OVERWRITE_IF_EXISTS_OR_ADD` append action. If the target header already exists it is overwritten; if it does not exist it is added. Use this plugin when you need to enforce a canonical header value at the proxy layer regardless of what the client or upstream originally sent — for example, normalising versioning headers, overriding client-supplied metadata, or stamping requests with a controlled value. It operates during the **request headers** and **response headers** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler calls `callout_tools.add_header_mutation` with `header-request: request-new-value`, the `OVERWRITE_IF_EXISTS_OR_ADD` append action, and `clear_route_cache=True`.
3. If `header-request` already exists in the request, its value is overwritten with `"request-new-value"`; if it does not exist, it is added. The route cache is cleared to force Envoy to recompute routing based on the updated header.
4. The modified request is forwarded to the upstream service.
5. When the upstream responds, the proxy invokes the plugin's `on_response_headers` callback.
6. The handler applies the same `OVERWRITE_IF_EXISTS_OR_ADD` action to set `header-response: response-new-value` on the outgoing response, without clearing the route cache.
7. The modified response is returned to the client.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_headers` | Overwrites or adds `header-request: request-new-value`; clears the route cache |
| `on_response_headers` | Overwrites or adds `header-response: response-new-value`; preserves the route cache |

## Key Code Walkthrough

- **Class structure** — `CalloutServerExample` extends `callout_server.CalloutServer` and overrides both header phase callbacks. No body-phase callbacks are registered, so request and response bodies pass through unmodified. The server is started by calling `.run()` directly on an instance.

- **Append action** — `HeaderValueOption.HeaderAppendAction` is imported from `envoy.config.core.v3.base_pb2` and aliased as `actions` at module level. The specific action used is `actions.OVERWRITE_IF_EXISTS_OR_ADD`, which instructs Envoy to replace the header value if the key is already present, or create a new header entry if it is not. This is distinct from the default append behaviour, which would add a duplicate header alongside any existing one.

- **Request header mutation** — `on_request_headers` calls `callout_tools.add_header_mutation` with `add=[('header-request', 'request-new-value')]`, `append_action=actions.OVERWRITE_IF_EXISTS_OR_ADD`, and `clear_route_cache=True`. Clearing the route cache ensures Envoy re-evaluates any routing rules that depend on the value of `header-request` after it has been overwritten.

- **Response header mutation** — `on_response_headers` follows the identical pattern with `add=[('header-response', 'response-new-value')]` and the same append action, but omits `clear_route_cache` (defaulting to `False`) since routing decisions are already finalised at the response phase.

- **Server startup** — The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required for the default setup. The header names, values, and append action are hardcoded directly in each callback:

- Request header overwritten or added: `header-request: request-new-value`
- Request phase route cache: cleared (`True`)
- Response header overwritten or added: `header-response: response-new-value`
- Response phase route cache: preserved (default `False`)
- Append action (both phases): `OVERWRITE_IF_EXISTS_OR_ADD`

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.update_header
```

Or run directly:
```bash
python update_header.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the update_header sample
python -m pytest tests/update_header_test.py

# With verbose output
python -m pytest -v tests/update_header_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request header overwritten** | Request containing `header-request` with any value | `header-request` value replaced with `"request-new-value"` |
| **Request header added** | Request without `header-request` | `header-request: request-new-value` added to request headers |
| **Request route cache cleared** | Any HTTP request | Envoy recomputes routing after request header mutation |
| **Response header overwritten** | Response containing `header-response` with any value | `header-response` value replaced with `"response-new-value"` |
| **Response header added** | Response without `header-response` | `header-response: response-new-value` added to response headers |
| **Response route cache preserved** | Any HTTP response | Envoy routing decision unchanged after response header mutation |
| **Body phases** | Any request or response body | Both body phases pass through unmodified; no body callbacks registered |

## Available Languages

- [x] [Python](update_header.py)