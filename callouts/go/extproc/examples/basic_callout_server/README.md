# Basic Callout Server Plugin

This plugin demonstrates a complete ext_proc callout service by handling all four HTTP processing phases simultaneously: request headers, response headers, request body, and response body. It injects a custom header into both the request and response, and replaces both the request and response bodies with predefined strings. Use this plugin as a reference implementation or starting point when you need a full-featured callout service that intercepts every phase of the HTTP lifecycle. It operates during the **request headers**, **response headers**, **request body**, and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `HandleRequestHeaders` handler.
2. The handler appends the header `header-request: Value-request` to the incoming request headers, preserving all existing headers.
3. The proxy then invokes `HandleRequestBody`, which replaces the incoming request body with the string `"new-body-request"`.
4. The modified request is forwarded to the upstream server.
5. When the upstream server responds, the proxy invokes `HandleResponseHeaders`, which appends `header-response: Value-response` to the outgoing response headers.
6. The proxy then invokes `HandleResponseBody`, which replaces the outgoing response body with the string `"new-body-response"`.
7. The fully modified response is returned to the client.

## gRPC Ext_Proc Handlers Used

| Handler | Purpose |
|---|---|
| `HandleRequestHeaders` | Intercepts incoming HTTP request headers and injects `header-request: Value-request` |
| `HandleResponseHeaders` | Intercepts outgoing HTTP response headers and injects `header-response: Value-response` |
| `HandleRequestBody` | Intercepts the incoming HTTP request body and replaces its content with `"new-body-request"` |
| `HandleResponseBody` | Intercepts the outgoing HTTP response body and replaces its content with `"new-body-response"` |

## Key Code Walkthrough

- **Service structure** — `ExampleCalloutService` embeds `server.GRPCCalloutService` and registers all four handlers in `NewExampleCalloutService()`. Each handler is assigned as a function reference on the `Handlers` struct, making this the most complete example of the standard service extension pattern.

- **Request header mutation** — `HandleRequestHeaders` receives an `*extproc.HttpHeaders` and returns a `ProcessingResponse` wrapping a `RequestHeaders` mutation. It calls `utils.AddHeaderMutation` with `{Key: "header-request", Value: "Value-request"}`, passing `nil` for headers to remove, `false` to preserve existing headers, and `nil` for additional options.

- **Response header mutation** — `HandleResponseHeaders` follows the identical pattern, injecting `{Key: "header-response", Value: "Value-response"}` into the outgoing response headers with the same non-destructive arguments.

- **Request body mutation** — `HandleRequestBody` receives an `*extproc.HttpBody` and returns a `ProcessingResponse` wrapping a `RequestBody` mutation. It calls `utils.AddBodyStringMutation("new-body-request", false)`, where `false` indicates the mutation should not clear the existing body before writing the new content.

- **Response body mutation** — `HandleResponseBody` follows the identical pattern, replacing the outgoing response body with `"new-body-response"` using the same non-clearing mutation.

- **Mutation utilities** — All four handlers delegate to shared helpers from the `pkg/utils` package: `utils.AddHeaderMutation` for header phase handlers and `utils.AddBodyStringMutation` for body phase handlers, both abstracting away the boilerplate of constructing the respective protobuf mutation messages.

## Configuration

No configuration required. All injected values are hardcoded directly in each handler:

- Request header: `header-request: Value-request`
- Response header: `header-response: Value-response`
- Request body replacement: `"new-body-request"`
- Response body replacement: `"new-body-response"`

## Build

Build the callout service from the repository root:
```bash
# Go
go build ./callouts/go/extproc/...
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests in the basic_callout_server package
go test ./callouts/go/extproc/samples/basic_callout_server/...

# With verbose output
go test -v ./callouts/go/extproc/samples/basic_callout_server/...
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request header is injected** | Any HTTP request | `header-request: Value-request` added to request headers |
| **Response header is injected** | Any HTTP response | `header-response: Value-response` added to response headers |
| **Request body is replaced** | Any HTTP request body | Body content replaced with `"new-body-request"` |
| **Response body is replaced** | Any HTTP response body | Body content replaced with `"new-body-response"` |
| **Existing headers are preserved** | Request or response with pre-existing headers | All original headers retained; `clear_headers` is `false` |
| **No headers are removed** | Any headers present | No headers stripped; remove list is `nil` |
| **Mutation is non-clearing** | Existing body present | Content overwritten without clearing; `clear_body` is `false` |

## Available Languages

- [x] [Go](add_header.go)
- [x] [Java](add_header.java)
- [x] [Python](add_header.py)
