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

## Implementation Notes

- **Header rewriting**: The plugin overwrites the `:authority` and `:path` pseudo-headers to redirect the request. Go handles errors with `defer recover()`.
- **Response modification**: Appends a custom `hello` header to the outgoing response.
- **Observability**: Logs a custom message during both the request and response phases.

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

| Scenario | Description |
|---|---|
| **Basics** (request) | Modifies an incoming request by rewriting the host and path headers while logging the action. |
| **Basics** (response) | Modifies an outgoing response by injecting a custom header while logging the action. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
