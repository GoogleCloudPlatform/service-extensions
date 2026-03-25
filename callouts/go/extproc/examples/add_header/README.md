# Add Header Plugin

This plugin modifies HTTP request and response headers by injecting custom key-value pairs into each phase. It intercepts both the incoming request headers and the outgoing response headers, adding a predefined header to each without removing or clearing existing ones. Use this plugin when you need to inject headers at the proxy layer for purposes such as request tagging, routing hints, or downstream metadata — without modifying application logic. It operates during the **request headers** and **response headers** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `HandleRequestHeaders` handler.
2. The handler appends the header `header-request: Value-request` to the incoming request headers, using a non-clearing, non-removing mutation that preserves all existing headers.
3. The modified request is forwarded to the upstream server.
4. When the upstream server responds, the proxy invokes the plugin's `HandleResponseHeaders` handler.
5. The handler appends the header `header-response: Value-response` to the outgoing response headers, following the same non-destructive mutation pattern.
6. The modified response is returned to the client.

## Implementation Notes

- **Service structure**: `ExampleCalloutService` embeds `server.GRPCCalloutService` and registers both header handlers in `NewExampleCalloutService()`. Handlers are assigned as function references on the `Handlers` struct, following the standard service extension pattern.
- **Request header mutation**: `HandleRequestHeaders` receives an `*extproc.HttpHeaders` and returns a `ProcessingResponse` wrapping a `RequestHeaders` mutation. It calls `utils.AddHeaderMutation` with a single `{Key: "header-request", Value: "Value-request"}` entry. The second and fourth arguments (`nil`) indicate no headers to remove and no additional options, while `false` signals that existing headers should not be cleared.
- **Response header mutation**: `HandleResponseHeaders` follows the identical pattern, wrapping a `ResponseHeaders` mutation with `{Key: "header-response", Value: "Value-response"}` using the same non-destructive arguments.
- **Mutation utility**: Both handlers delegate to `utils.AddHeaderMutation`, a shared helper from the `pkg/utils` package. It accepts a slice of key-value structs to add, a slice of header keys to remove, a boolean to clear all existing headers, and an optional additional options argument — abstracting away the boilerplate of building the `HeaderMutation` protobuf message.

## Configuration

No configuration required. The injected header names and values are hardcoded directly in each handler:
- `request header`: `header-request: Value-request`
- `response header`: `header-response: Value-response`

## Build

Build the callout service from the repository root:
```bash
# Go
go build ./callouts/go/extproc/...
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests in the add_header package
go test ./callouts/go/extproc/samples/add_header/...

# With verbose output
go test -v ./callouts/go/extproc/samples/add_header/...
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request header is injected** | Any incoming HTTP request gets `header-request: Value-request` added to its headers. |
| **Response header is injected** | Any outgoing HTTP response gets `header-response: Value-response` added to its headers. |
| **Existing headers are preserved** | All original headers are retained; `clear_headers` is `false`. |
| **No headers are removed** | No headers are stripped; the remove list is `nil`. |

## Available Languages

- [x] [Go](add_header.go)
- [x] [Java](add_header.java)
- [x] [Python](add_header.py)
