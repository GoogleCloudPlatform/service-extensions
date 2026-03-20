# Dynamic Forwarding Plugin

This plugin implements dynamic backend routing by extracting a target IP address from an incoming request header and embedding it as dynamic metadata on the processing response. Envoy reads this metadata to forward the request to the specified backend at runtime, enabling per-request routing decisions without static cluster configuration. Use this plugin when you need to route individual requests to different upstream backends based on request-level context, such as user identity, tenant ID, or custom routing headers. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `HandleRequestHeaders` handler.
2. The handler inspects the incoming headers looking for a custom `ip-to-return` header.
3. If the `ip-to-return` header is present, its value is used as the target backend IP address.
4. If the header is absent or the headers object is nil, the handler falls back to a hardcoded default backend IP of `10.1.10.3`.
5. The resolved IP address and port `80` are passed to `utils.AddDynamicForwardingMetadata`, which constructs the appropriate protobuf metadata structure.
6. The handler returns a `ProcessingResponse` with an empty `HeadersResponse` and the dynamic metadata attached, signalling Envoy to forward the request to the resolved backend.

## gRPC Ext_Proc Handlers Used

| Handler | Purpose |
|---|---|
| `HandleRequestHeaders` | Extracts the `ip-to-return` header and sets dynamic forwarding metadata to route the request to the resolved backend |

## Key Code Walkthrough

- **Service structure** — `ExampleCalloutService` embeds `server.GRPCCalloutService` and registers only the request headers handler in `NewExampleCalloutService()`, as dynamic forwarding decisions must be made before the request reaches the upstream.

- **Header extraction** — `extractIpToReturnHeader` iterates over the raw header list in `headers.Headers.Headers`, matching on `header.Key == "ip-to-return"` and returning the value of `header.RawValue` as a string. It returns an error if the headers object is nil or if no matching header is found, allowing the caller to apply a fallback.

- **Fallback routing** — If `extractIpToReturnHeader` returns an error (header missing or nil input), `HandleRequestHeaders` silently falls back to `"10.1.10.3"` as the default backend IP. This ensures the plugin never blocks a request due to a missing routing hint.

- **Dynamic metadata construction** — `utils.AddDynamicForwardingMetadata(ipToReturn, 80)` builds a protobuf `Struct` containing the target IP and port in the format Envoy expects for dynamic forwarding. The result is attached to the `ProcessingResponse` via the `DynamicMetadata` field, not through header mutation.

- **Response structure** — The returned `ProcessingResponse` carries an empty `HeadersResponse` (no header mutations are applied) alongside the populated `DynamicMetadata`, keeping header processing transparent while still influencing upstream routing.

## Configuration

No configuration required. The fallback backend and forwarding port are hardcoded as constants in the handler:

- Default backend IP: `10.1.10.3`
- Forwarding port: `80`
- Routing header: `ip-to-return`

## Build

Build the callout service from the repository root:
```bash
# Go
go build ./callouts/go/extproc/...
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests in the dynamic_forwarding package
go test ./callouts/go/extproc/samples/dynamic_forwarding/...

# With verbose output
go test -v ./callouts/go/extproc/samples/dynamic_forwarding/...
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Custom backend is used** | Request with `ip-to-return: 192.168.1.5` | Dynamic metadata set to `192.168.1.5:80`; request forwarded to custom backend |
| **Default backend is used** | Request without `ip-to-return` header | Dynamic metadata set to `10.1.10.3:80`; request forwarded to default backend |
| **Nil headers fallback** | Nil or empty headers object | Dynamic metadata set to `10.1.10.3:80`; no error returned to proxy |
| **Metadata build failure** | `AddDynamicForwardingMetadata` returns error | Handler returns `nil` response and propagates the error to the proxy |
| **No header mutations** | Any request | Headers pass through unmodified; only `DynamicMetadata` is populated |

## Available Languages

- [x] [Go](dynamic_forwarding.go)
- [x] [Python](dynamic_forwarding.py)