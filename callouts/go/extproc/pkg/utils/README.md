# Utils Library

This package provides the shared mutation helper functions used across all callout service samples. It abstracts the construction of protobuf `ProcessingResponse` sub-messages for the most common ext_proc operations: adding or removing headers, replacing or clearing body content, issuing immediate HTTP responses, and attaching dynamic forwarding metadata. Use this package as the single source of truth for building well-formed ext_proc mutation messages — all sample plugins delegate to these helpers rather than constructing protobuf structs directly.

## How It Works

Each function in this package accepts high-level parameters (strings, slices, status codes) and returns a fully constructed protobuf message ready to be embedded in a `ProcessingResponse`. The caller is responsible only for wrapping the returned value in the appropriate `ProcessingResponse` variant. No network I/O, no side effects — these are pure builder functions.

## Functions

| Function | Returns | Purpose |
|---|---|---|
| `AddHeaderMutation` | `*extproc.HeadersResponse` | Adds and/or removes headers, optionally clearing the route cache |
| `HeaderImmediateResponse` | `*extproc.ImmediateResponse` | Builds an immediate HTTP response with a status code and headers |
| `AddBodyStringMutation` | `*extproc.BodyResponse` | Replaces the body with a UTF-8 string |
| `AddBodyClearMutation` | `*extproc.BodyResponse` | Clears the body entirely |
| `AddDynamicForwardingMetadata` | `*structpb.Struct, error` | Constructs dynamic forwarding metadata for per-request backend routing |

## Key Code Walkthrough

- **`AddHeaderMutation(add, remove, clearRouteCache, appendAction)`** — Iterates over the `add` slice of `{Key, Value}` structs and builds a `base.HeaderValueOption` for each, storing the value as `RawValue []byte`. If `appendAction` is non-nil, it is set on each option to control whether headers are appended or overwritten. The `remove` slice is appended directly to `headerMutation.RemoveHeaders`. Both the mutation and `ClearRouteCache` flag are wrapped in a `CommonResponse` inside a `HeadersResponse`.

- **`HeaderImmediateResponse(code, addHeaders, removeHeaders, appendAction)`** — Delegates header construction entirely to `AddHeaderMutation`, then deep-clones the resulting `HeaderMutation` via `proto.Clone` to safely embed it in an `ImmediateResponse`. The HTTP status code is wrapped in an `HttpStatus` message. This is the only function in the package that uses `proto.Clone`, ensuring the cloned mutation is independent of the one produced by `AddHeaderMutation`.

- **`AddBodyStringMutation(body, clearRouteCache)`** — Converts the `body` string to `[]byte` and sets it as the `BodyMutation_Body` variant inside a `BodyMutation`. The mutation and `ClearRouteCache` flag are wrapped in a `CommonResponse` inside a `BodyResponse`.

- **`AddBodyClearMutation(clearRouteCache)`** — Constructs a `BodyMutation` using the `BodyMutation_ClearBody` variant with `ClearBody: true`, instructing Envoy to remove the body entirely. Follows the same `CommonResponse` wrapping pattern as `AddBodyStringMutation`.

- **`AddDynamicForwardingMetadata(ipAddress, portNumber)`** — Formats the address as `"<ip>:<port>"` and builds a `structpb.Struct` with the key `com.google.envoy.dynamic_forwarding.selected_endpoints` mapped to `{"primary": "<ip>:<port>"}`. This namespace is the contract expected by Envoy's dynamic forwarding filter and is defined as the package-level constant `DYNAMIC_FORWARDING_METADATA_NAMESPACE`.

## Constants

| Constant | Value | Purpose |
|---|---|---|
| `DYNAMIC_FORWARDING_METADATA_NAMESPACE` | `com.google.envoy.dynamic_forwarding.selected_endpoints` | Metadata key namespace expected by Envoy's dynamic forwarding filter |

## Function Signatures
```go
func AddHeaderMutation(
    add []struct{ Key, Value string },
    remove []string,
    clearRouteCache bool,
    appendAction *base.HeaderValueOption_HeaderAppendAction,
) *extproc.HeadersResponse

func HeaderImmediateResponse(
    code httpstatus.StatusCode,
    addHeaders []struct{ Key, Value string },
    removeHeaders []string,
    appendAction *base.HeaderValueOption_HeaderAppendAction,
) *extproc.ImmediateResponse

func AddBodyStringMutation(body string, clearRouteCache bool) *extproc.BodyResponse

func AddBodyClearMutation(clearRouteCache bool) *extproc.BodyResponse

func AddDynamicForwardingMetadata(ipAddress string, portNumber int) (*structpb.Struct, error)
```

## Build

Build the utils package from the repository root:
```bash
# Go
go build ./callouts/go/extproc/pkg/utils/...
```

## Test

Run the unit tests for the utils package:
```bash
# Run all tests in the utils package
go test ./callouts/go/extproc/pkg/utils/...

# With verbose output
go test -v ./callouts/go/extproc/pkg/utils/...
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Headers added** | `add` slice with one or more entries | `SetHeaders` populated on `HeaderMutation` |
| **Headers removed** | Non-nil `remove` slice | `RemoveHeaders` populated on `HeaderMutation` |
| **Append action set** | Non-nil `appendAction` | Each `HeaderValueOption` carries the specified append action |
| **Route cache cleared** | `clearRouteCache: true` | `ClearRouteCache: true` on the `CommonResponse` |
| **Immediate response** | Status code + headers | `ImmediateResponse` with `HttpStatus` and cloned `HeaderMutation` |
| **Body replaced** | Non-empty string | `BodyMutation_Body` set to UTF-8 bytes of the string |
| **Body cleared** | `AddBodyClearMutation` called | `BodyMutation_ClearBody: true` on the `BodyMutation` |
| **Dynamic metadata built** | `"192.168.1.1"`, `8080` | Struct with key `com.google.envoy.dynamic_forwarding.selected_endpoints` → `{"primary": "192.168.1.1:8080"}` |
| **Dynamic metadata error** | Invalid struct value | `structpb.NewStruct` returns non-nil error; caller receives `nil, err` |

## Available Languages

- [x] [Go](utils.go)