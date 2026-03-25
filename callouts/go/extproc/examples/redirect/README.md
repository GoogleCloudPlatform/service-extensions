# Redirect Plugin

This plugin implements an unconditional HTTP redirect at the proxy layer by intercepting every incoming request and immediately returning a `301 Moved Permanently` response with a hardcoded `Location` header, before the request ever reaches the upstream service. Use this plugin when you need to enforce a blanket redirect for all traffic through a proxy — such as domain migrations, protocol enforcement, or legacy endpoint retirement — without involving any backend logic. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `HandleRequestHeaders` handler.
2. The handler unconditionally constructs an immediate response with HTTP status `301`.
3. A `Location: http://service-extensions.com/redirect` header is attached to the immediate response.
4. The `ProcessingResponse` is returned with an `ImmediateResponse` variant, instructing Envoy to short-circuit the request and send the redirect directly to the client.
5. The upstream service is never contacted.

## Implementation Notes

- **Service structure**: `ExampleCalloutService` embeds `server.GRPCCalloutService` and registers only the request headers handler in `NewExampleCalloutService()`. No other phases are needed since the request is terminated before reaching the body or response phases.
- **Immediate response**: `HandleRequestHeaders` returns a `ProcessingResponse` wrapping a `ProcessingResponse_ImmediateResponse` variant rather than a `ProcessingResponse_RequestHeaders` variant. This tells Envoy to stop processing the request and reply to the client directly, bypassing the upstream entirely.
- **Redirect construction**: The immediate response is built by `utils.HeaderImmediateResponse(301, headers, body, trailers)`, a shared utility that constructs the `ImmediateResponse` protobuf message. The status code is `301`, the headers slice contains a single `Location: http://service-extensions.com/redirect` entry, and both the body and trailers arguments are `nil`.
- **Unconditional behaviour**: Unlike routing or filtering plugins, this handler performs no inspection of the incoming request. Every request — regardless of path, method, or headers — receives the same redirect response.

## Configuration

No configuration required. The redirect target and status code are hardcoded directly in the handler:
- `HTTP status code`: `301` (Moved Permanently)
- `redirect target`: `http://service-extensions.com/redirect`
- `response body`: none
- `response trailers`: none

## Build

Build the callout service from the repository root:
```bash
# Go
go build ./callouts/go/extproc/...
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests in the redirect package
go test ./callouts/go/extproc/samples/redirect/...

# With verbose output
go test -v ./callouts/go/extproc/samples/redirect/...
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Any request is redirected** | Every HTTP request, regardless of path or method, receives a `301 Moved Permanently` with `Location: http://service-extensions.com/redirect`. |
| **Upstream is never reached** | The request is short-circuited at the proxy on every call; no upstream connection is made. |
| **No body in response** | The immediate response is returned with no body content. |
| **No trailers in response** | The immediate response is returned with no trailers. |

## Available Languages

- [x] [Go](redirect.go)
- [x] [Java](redirect.java)
- [x] [Python](redirect.py)
