# Add Response Header Plugin

This plugin modifies HTTP response headers as they pass through the proxy. It conditionally appends a value to the `Message` header when it equals `foo`, and unconditionally removes the `Welcome` header from all responses. Use this plugin when you need to manipulate response headers based on their current values, inject metadata into responses, or remove sensitive headers before responses reach clients. It operates during the **response headers** processing phase.

## How It Works

1. The proxy receives an HTTP response from the upstream server and invokes the plugin's `on_http_response_headers` callback.
2. The plugin reads the `Message` response header and checks if its value equals `"foo"`.
3. If the `Message` header equals `"foo"`, the plugin appends `"bar"` to it (resulting in `"foo, bar"`). If the header doesn't exist or has a different value, no modification is made.
4. The plugin unconditionally removes the `Welcome` header from the response, regardless of its value.
5. The plugin returns `Action::Continue`, forwarding the modified response headers to the client.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_response_headers` | Conditionally appends to the `Message` header and removes the `Welcome` header |

## Key Code Walkthrough

The core logic is identical across all three language implementations:

- **Conditional header modification** — The plugin reads the `Message` header and conditionally adds a value:
  - **C++** uses `getResponseHeader("Message")` to retrieve the header, checks if `msg->view() == "foo"`, and calls `addResponseHeader("Message", "bar")` to append `"bar"`.
  - **Go** uses `proxywasm.GetHttpResponseHeader("Message")` to retrieve the header, checks if `msgValue == "foo"`, and calls `proxywasm.AddHttpResponseHeader("Message", "bar")` to append `"bar"`. If the header is missing, the error is logged as critical but does not stop processing.
  - **Rust** uses `self.get_http_response_header("Message")` with `unwrap_or_default()` to retrieve the header (defaulting to an empty string if missing), checks if it equals `"foo"`, and calls `self.add_http_response_header("Message", "bar")` to append `"bar"`.

  The **add** operation appends the new value with a comma separator (e.g., `"foo"` becomes `"foo, bar"`), following standard HTTP header semantics for multi-valued headers.

- **Unconditional header removal** — The plugin removes the `Welcome` header:
  - **C++** uses `removeResponseHeader("Welcome")`.
  - **Go** uses `proxywasm.RemoveHttpResponseHeader("Welcome")`. If the removal fails (e.g., header doesn't exist), it triggers a panic.
  - **Rust** uses `self.set_http_response_header("Welcome", None)` (setting a header to `None` removes it).

- **Error handling** — Error handling differs slightly between implementations:
  - **C++** performs no explicit error handling (relies on the host context).
  - **Go** includes a `defer recover()` block that catches panics and sends a 500 error response. Missing `Message` headers are logged but do not interrupt processing.
  - **Rust** handles missing headers gracefully with `unwrap_or_default()`.

## Configuration

No configuration required.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/add_response_header:plugin_rust.wasm

# C++
bazelisk build //samples/add_response_header:plugin_cpp.wasm

# Go
bazelisk build //samples/add_response_header:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/add_response_header/tests.textpb \
    --plugin /mnt/bazel-bin/samples/add_response_header/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/add_response_header:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **NoDefaultResponseHeader** | Response with no `Message` header | No `Message` header added (conditional logic does not trigger) |
| **LeavesResponseHeader** | Response with `Message: non-matching` | `Message: non-matching` unchanged (value does not equal `"foo"`) |
| **ExtendsResponseHeader** | Response with `Message: foo` | `Message: foo, bar` (value appended because original equals `"foo"`) |
| **RemovesResponseHeader** | Response with `Welcome: any` | `Welcome` header removed (unconditional removal) |
| **RequestAndResponse** | Response with `Message: foo` | `Message: foo, bar` (behavior consistent across request/response phases) |
| **CaseInsensitiveLookup** | Response with `message: foo` (lowercase) | `message: foo, bar` (header names are case-insensitive) |
| **CaseInsensitiveRemoval** | Response with `welcome: any` (lowercase) | `welcome` header removed (case-insensitive removal) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
