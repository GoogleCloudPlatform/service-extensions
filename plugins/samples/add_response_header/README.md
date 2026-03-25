# Add Response Header Plugin

This plugin modifies HTTP response headers as they pass through the proxy. It conditionally appends a value to the `Message` header when it equals `foo`, and unconditionally removes the `Welcome` header from all responses. Use this plugin when you need to manipulate response headers based on their current values, inject metadata into responses, or remove sensitive headers before responses reach clients. It operates during the **response headers** processing phase.

## How It Works

1. The proxy receives an HTTP response from the upstream server and invokes the plugin's `on_http_response_headers` callback.
2. The plugin reads the `Message` response header and checks if its value equals `"foo"`.
3. If the `Message` header equals `"foo"`, the plugin appends `"bar"` to it (resulting in `"foo, bar"`). If the header doesn't exist or has a different value, no modification is made.
4. The plugin unconditionally removes the `Welcome` header from the response, regardless of its value.
5. The plugin returns `Action::Continue`, forwarding the modified response headers to the client.

## Implementation Notes

- **Appending headers**: The `Message` header is modified using the "add" operation, which appropriately appends values automatically separated by commas.
- **Removing headers**: The `Welcome` header is removed unconditionally. In Rust, this is achieved by trying to set the header to `None`.
- **Error handling considerations**: Missing headers need to be handled carefully depending on the target language. The Go implementation uses `defer recover()` to respond with a 500 error if panics occur during header manipulation, while Rust handles them gracefully via `unwrap_or_default()`.

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

| Scenario | Description |
|---|---|
| **NoDefaultResponseHeader** | Applies no changes if the required header is missing. |
| **LeavesResponseHeader** | Makes no modifications if the header value does not match the expected string. |
| **ExtendsResponseHeader** | Appends a value to the header when the original value matches. |
| **RemovesResponseHeader** | Unconditionally removes the specified header. |
| **RequestAndResponse** | Confirms behavior correctly matches the response phase. |
| **CaseInsensitiveLookup** | Successfully detects and appends to the header regardless of its casing. |
| **CaseInsensitiveRemoval** | Successfully removes the specified header even when casing differs. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
