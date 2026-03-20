# Dynamic Forwarding Plugin (Python)

This plugin implements dynamic backend routing by extracting a target IP address from an incoming request header and embedding it as dynamic metadata on the processing response. Envoy reads this metadata to forward the request to the specified backend at runtime, enabling per-request routing decisions without static cluster configuration. Use this plugin when you need to route individual requests to different upstream backends based on request-level context, such as a custom routing header carrying a target IP. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler iterates over the incoming headers looking for a header named `ip-to-return` and decodes its raw value as UTF-8.
3. The extracted IP is validated against a list of two known addresses: `10.1.10.2` and `10.1.10.3`.
4. If the extracted IP matches one of the known addresses, it is used as the target backend IP.
5. If the `ip-to-return` header is absent, malformed, or its value is not in the known addresses list, the handler falls back to the default IP `10.1.10.4`.
6. The selected IP and port `80` are passed to `callout_tools.build_dynamic_forwarding_metadata` to construct the appropriate protobuf metadata structure.
7. The handler returns a `ProcessingResponse` with an empty `HeadersResponse` and the dynamic metadata attached, signalling Envoy to forward the request to the resolved backend.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_headers` | Extracts `ip-to-return` header, validates against known addresses, and sets dynamic forwarding metadata to route the request to the resolved backend |

## Key Code Walkthrough

- **Class structure** — `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the request headers callback. No other phases are registered, so all other HTTP lifecycle phases pass through unmodified. The server is started by calling `.run()` directly on an instance.

- **Header extraction** — The callback uses a generator expression with `next(..., None)` to iterate over `headers.headers.headers`, matching on `header.key == 'ip-to-return'` and decoding `header.raw_value` as UTF-8. The `None` default means a missing header is handled gracefully without raising an exception.

- **Address validation** — The extracted IP is checked with `if ip_to_return not in known_addresses`, where `known_addresses = ['10.1.10.2', '10.1.10.3']`. Any value outside this list — including `None` from a missing header — causes the fallback IP `10.1.10.4` to be used instead. The selected IP is logged at `DEBUG` level.

- **Dynamic metadata construction** — `callout_tools.build_dynamic_forwarding_metadata(ip_address=ip_to_return, port_number=80)` builds the protobuf `Struct` containing the target endpoint in the format expected by Envoy's dynamic forwarding filter.

- **Response structure** — The handler returns a `service_pb2.ProcessingResponse` directly (rather than a `HeadersResponse`), populating both `request_headers=service_pb2.HeadersResponse()` (an empty pass-through) and `dynamic_metadata=selected_endpoints`. This keeps header processing transparent while still influencing upstream routing via the metadata field.

- **Server startup** — The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required for the default setup. The known address list, fallback IP, and forwarding port are hardcoded in the callback:

- Known addresses: `10.1.10.2`, `10.1.10.3`
- Default (fallback) backend IP: `10.1.10.4`
- Forwarding port: `80`
- Routing header: `ip-to-return`

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.dynamic_forwarding
```

Or run directly:
```bash
python dynamic_forwarding.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the dynamic_forwarding sample
python -m pytest tests/dynamic_forwarding_test.py

# With verbose output
python -m pytest -v tests/dynamic_forwarding_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **First known address selected** | `ip-to-return: 10.1.10.2` | Dynamic metadata set to `10.1.10.2:80`; request forwarded to first known backend |
| **Second known address selected** | `ip-to-return: 10.1.10.3` | Dynamic metadata set to `10.1.10.3:80`; request forwarded to second known backend |
| **Unknown address falls back** | `ip-to-return: 192.168.1.5` | Dynamic metadata set to `10.1.10.4:80`; request forwarded to default backend |
| **Missing header falls back** | Request without `ip-to-return` header | Dynamic metadata set to `10.1.10.4:80`; request forwarded to default backend |
| **No header mutations** | Any request | Headers pass through unmodified; only `dynamic_metadata` is populated |
| **Response phases** | Any HTTP response | All response phases pass through unmodified; no response callbacks registered |

## Available Languages

- [x] [Python](dynamic_forwarding.py)