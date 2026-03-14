# First Plugin

This plugin is a simple introductory example that demonstrates basic request and response header manipulation. It rewrites the host (`:authority`) and path (`:path`) of incoming requests and adds a custom header to outgoing responses. Use this plugin as a starting point for learning Proxy-WASM development or as a template for building more complex plugins. It operates during the **request headers** and **response headers** processing phases.

## How It Works

1. **Request processing**: When the proxy receives an HTTP request from a client, it invokes the plugin's `on_http_request_headers` callback.
   - The plugin logs `"onRequestHeaders: hello from wasm"` to the proxy logs.
   - The plugin rewrites the `:authority` pseudo-header to `"service-extensions.com"` (effectively changing the destination host).
   - The plugin rewrites the `:path` pseudo-header to `"/"` (changing the request path to the root).
   - The plugin returns `Action::Continue`, forwarding the modified request to the upstream server.

2. **Response processing**: When the proxy receives an HTTP response from the upstream server, it invokes the plugin's `on_http_response_headers` callback.
   - The plugin logs `"onResponseHeaders: hello from wasm"` to the proxy logs.
   - The plugin adds a `hello: service-extensions` header to the response.
   - The plugin returns `Action::Continue`, forwarding the modified response to the client.

This plugin demonstrates two common Service Extensions use cases:
- **Route Extension**: Rewriting the destination host and path (`:authority` and `:path` headers) to route requests to different backends.
- **Traffic Extension**: Adding custom headers to responses for debugging, tracing, or client identification.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Logs a message and rewrites the `:authority` and `:path` headers to route requests to `service-extensions.com/` |
| `on_http_response_headers` | Logs a message and adds the `hello: service-extensions` header to the response |

## Key Code Walkthrough

The core logic is identical across all three language implementations:

- **Request header rewriting** — The plugin modifies routing headers:
  - **C++** uses `replaceRequestHeader(":authority", "service-extensions.com")` and `replaceRequestHeader(":path", "/")` to overwrite the pseudo-headers.
  - **Go** uses `proxywasm.ReplaceHttpRequestHeader(":authority", "service-extensions.com")` and `proxywasm.ReplaceHttpRequestHeader(":path", "/")`. Errors trigger a panic, which is caught by the `defer recover()` block and results in a 500 error response.
  - **Rust** uses `self.set_http_request_header(":authority", Some("service-extensions.com"))` and `self.set_http_request_header(":path", Some("/"))`.

  The **`:authority`** pseudo-header is the HTTP/2 equivalent of the HTTP/1.1 `Host` header and controls which upstream server receives the request. The **`:path`** pseudo-header specifies the request URI path.

- **Response header addition** — The plugin adds a custom header to responses:
  - **C++** uses `addResponseHeader("hello", "service-extensions")` to add the header. If the header already exists, the value is appended (comma-separated).
  - **Go** uses `proxywasm.AddHttpResponseHeader("hello", "service-extensions")` with the same append semantics.
  - **Rust** uses `self.add_http_response_header("hello", "service-extensions")` with the same append semantics.

- **Logging** — Both callbacks log messages:
  - **C++** uses `LOG_INFO("onRequestHeaders: hello from wasm")` and `LOG_INFO("onResponseHeaders: hello from wasm")`.
  - **Go** uses `proxywasm.LogInfof("onRequestHeaders: hello from wasm")` and `proxywasm.LogInfof("onResponseHeaders: hello from wasm")`.
  - **Rust** uses `info!("onRequestHeaders: hello from wasm")` and `info!("onResponseHeaders: hello from wasm")`.

  These log messages appear in the proxy's logs and are useful for debugging and tracing plugin execution.

## Configuration

No configuration required.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/first_plugin:plugin_rust.wasm

# C++
bazelisk build //samples/first_plugin:plugin_cpp.wasm

# Go
bazelisk build //samples/first_plugin:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/first_plugin/tests.textpb \
    --plugin /mnt/bazel-bin/samples/first_plugin/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/first_plugin:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **Basics** (request) | Any HTTP request | Log message matching `onRequestHeaders: hello from wasm`; `:authority: service-extensions.com`; `:path: /` (request routed to `service-extensions.com/` regardless of original destination) |
| **Basics** (response) | Any HTTP response | Log message matching `onResponseHeaders: hello from wasm`; `hello: service-extensions` header added |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
