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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Immediately sends a "Hello World" response and stops request processing |
| `on_http_request_body` (C++ only) | No-op (returns `Continue`); included for completeness |
| `on_http_response_headers` | No-op (returns `Continue`); included for completeness (never reached since request is intercepted) |
| `on_http_response_body` (Go only) | No-op (returns `Continue`); included for completeness (never reached) |

## Key Code Walkthrough

The core logic is identical across all three language implementations:

- **Sending local response** — The plugin generates an immediate HTTP response:
  - **C++**:
    ```cpp
    sendLocalResponse(200, "", "Hello World",
                      {{"Content-Type", "text/plain"}, {":status", "200"}});
    return FilterHeadersStatus::StopIteration;
    ```
    - First argument: HTTP status code (200)
    - Second argument: Additional details (empty string)
    - Third argument: Response body (`"Hello World"`)
    - Fourth argument: Headers as a vector of pairs
    - Return value stops further request processing

  - **Go**:
    ```go
    proxywasm.SendHttpResponse(200, [][2]string{
        {"Content-Type", "text/plain"},
        {":status", "200"},
    }, []byte("Hello World"), -1)
    return types.ActionPause
    ```
    - First argument: HTTP status code (200)
    - Second argument: Headers as a slice of 2-element arrays
    - Third argument: Response body as byte slice
    - Fourth argument: gRPC status (-1 means no gRPC status)
    - Return value pauses request processing

  - **Rust**:
    ```rust
    self.send_http_response(
        200, 
        vec![("Content-Type", "text/plain")], 
        Some(b"Hello World")
    );
    return Action::Pause;
    ```
    - First argument: HTTP status code (200)
    - Second argument: Headers as a vector of tuples
    - Third argument: Optional response body as byte slice
    - Return value pauses request processing

- **Stopping request processing** — All implementations prevent the request from reaching the upstream server:
  - **C++**: `FilterHeadersStatus::StopIteration` — Stops iterating through the filter chain and sends the local response.
  - **Go**: `types.ActionPause` — Pauses request processing and sends the immediate response.
  - **Rust**: `Action::Pause` — Pauses request processing and sends the immediate response.

- **No-op callbacks** — Additional callbacks are implemented but do nothing:
  - These callbacks are included for completeness and to demonstrate the plugin structure.
  - They are never invoked because the request is intercepted during `on_http_request_headers`.

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

| Scenario | Input | Output |
|---|---|---|
| **SendHelloWorldResponse** | Any HTTP request | 200 OK response with `Content-Type: text/plain` header and body containing `"Hello World"` (request never reaches upstream server) |

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
