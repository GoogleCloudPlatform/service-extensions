# Hello World Plugin

This plugin is the simplest possible example that demonstrates how to send an immediate HTTP response from a Proxy-WASM plugin. For every incoming request, the plugin intercepts it and immediately returns a "Hello World" response with status 200, bypassing the upstream server entirely. Use this plugin as an introduction to Proxy-WASM development, for testing plugin deployment, or as a template for building more complex response-generating plugins. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. The plugin immediately sends a local HTTP response with:
   - **Status code**: 200 (OK)
   - **Headers**: `Content-Type: text/plain`
   - **Body**: `"Hello World"`

3. The plugin returns a status that stops further processing:
   - **C++**: `FilterHeadersStatus::StopIteration`
   - **Go**: `types.ActionPause`
   - **Rust**: `Action::Pause`

4. The proxy sends the response directly to the client **without** forwarding the request to the upstream server.

This plugin demonstrates the fundamental capability of Proxy-WASM plugins to intercept requests and generate responses, which is the basis for more complex plugins like authentication, rate limiting, or dynamic content generation.

## Implementation Notes

- **Immediate response generation**: Constructs an HTTP response locally within the plugin, leveraging `sendLocalResponse` in C++, `SendHttpResponse` in Go, and `send_http_response` in Rust.
- **Circuit breaking**: Halts the request processing chain entirely by returning `StopIteration` (C++) or `Pause` (Go/Rust), ensuring no traffic reaches upstream servers.
- **No-op fallbacks**: Contains unimplemented callbacks specifically to illustrate plugin lifecycle capabilities against early termination.

## Configuration

No configuration required.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/hello_world:plugin_rust.wasm

# C++
bazelisk build //samples/hello_world:plugin_cpp.wasm

# Go
bazelisk build //samples/hello_world:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/hello_world/tests.textpb \
    --plugin /mnt/bazel-bin/samples/hello_world/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/hello_world:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **SendHelloWorldResponse** | Intercepts the request and responds locally with a 200 OK and a "Hello World" plain text body. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Learning Objectives

This plugin demonstrates:

1. **Immediate response generation**: How to send an HTTP response directly from a plugin without reaching the upstream server.

2. **Request interception**: How to stop request processing and prevent forwarding to upstream services.

3. **Basic plugin structure**: The minimal code required for a working Proxy-WASM plugin in each language:
   - Context registration
   - HTTP context creation
   - Request header callback implementation

4. **Response format**: How to construct an HTTP response with status code, headers, and body.

5. **Return values**: The different return types (`FilterHeadersStatus`, `types.Action`, `Action`) and their effects on request processing.

## Next Steps

After understanding this plugin, explore more complex examples:
- **`first_plugin`**: Header manipulation and logging
- **`add_response_header`**: Conditional header modification
- **`block_request`**: Token-based access control
- **`hmac_authtoken`**: Cryptographic authentication
