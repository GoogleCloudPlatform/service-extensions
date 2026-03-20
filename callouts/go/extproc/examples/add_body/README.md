# Add Body Plugin

This plugin modifies HTTP request and response bodies by replacing their content with predefined strings. It intercepts both the incoming request body and the outgoing response body, substituting each with a new hardcoded value. Use this plugin when you need to replace or inject body content at the proxy layer without modifying application logic. It operates during the **request body** and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `HandleRequestBody` handler.
2. The handler replaces the incoming request body with the string `"new-body-request"`, using a non-clearing mutation (preserving existing body structure while overwriting content).
3. The modified request is forwarded to the upstream server.
4. When the upstream server responds, the proxy invokes the plugin's `HandleResponseBody` handler.
5. The handler replaces the outgoing response body with the string `"new-body-response"`, again using a non-clearing mutation.
6. The modified response is returned to the client.

## gRPC Ext_Proc Handlers Used

| Handler | Purpose |
|---|---|
| `HandleRequestBody` | Intercepts the incoming HTTP request body and replaces its content with `"new-body-request"` |
| `HandleResponseBody` | Intercepts the outgoing HTTP response body and replaces its content with `"new-body-response"` |

## Key Code Walkthrough

- **Service structure** — `ExampleCalloutService` embeds `server.GRPCCalloutService` and registers both body handlers in `NewExampleCalloutService()`. This follows the standard service extension pattern where handlers are assigned as function references on the `Handlers` struct.

- **Request body mutation** — `HandleRequestBody` receives an `*extproc.HttpBody` and returns a `ProcessingResponse` wrapping a `RequestBody` mutation. It calls `utils.AddBodyStringMutation("new-body-request", false)`, where the `false` argument indicates the mutation should not clear the existing body before setting the new content.

- **Response body mutation** — `HandleResponseBody` follows the identical pattern, wrapping a `ResponseBody` mutation with `utils.AddBodyStringMutation("new-body-response", false)`.

- **Mutation utility** — Both handlers delegate to `utils.AddBodyStringMutation`, a shared helper from the `pkg/utils` package that constructs the appropriate `BodyMutation` protobuf message, abstracting away the boilerplate of building the `ProcessingResponse`.

## Configuration

No configuration required. The replacement body strings are hardcoded directly in each handler:

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
# Run all tests in the add_body package
go test ./callouts/go/extproc/samples/add_body/...

# With verbose output
go test -v ./callouts/go/extproc/samples/add_body/...
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request body is replaced** | Any HTTP request body | Body content replaced with `"new-body-request"` |
| **Response body is replaced** | Any HTTP response body | Body content replaced with `"new-body-response"` |
| **Mutation is non-clearing** | Existing body present | Content overwritten without clearing; `clear_body` is `false` |

## Available Languages

- [x] [Go](add_body.go)
- [x] [Java](add_body.java)
- [x] [Python](add_body.py)
