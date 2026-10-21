# Add Request Header Plugin

This plugin adds and sets HTTP headers on client requests as they pass through
the proxy. It demonstrates the distinction between **adding** a header (which
appends to any existing value) and **setting/replacing** a header (which
overwrites any existing value). Use this plugin when you need to inject metadata,
routing hints, or default values into upstream requests. It operates during the
**request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's
   `on_http_request_headers` callback.
2. The plugin **adds** a `Message: hello` header. If the request already
   contains a `Message` header, the new value is appended (comma-separated),
   resulting in `Message: <original>, hello`.
3. The plugin **sets** the `Welcome` header to `warm`. If the request already
   contains a `Welcome` header, the existing value is replaced entirely.
4. The plugin returns `Action::Continue`, allowing the (now modified) request to
   proceed to the upstream server.

## Implementation Notes

- **Appending vs replacing headers**: This plugin demonstrates the distinction between "adding" a header (appending with a comma to existing values if present) and "setting" or "replacing" a header (completely overwriting it).

## Configuration

No configuration required.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/add_request_header:plugin_rust.wasm

# C++
bazelisk build //samples/add_request_header:plugin_cpp.wasm

# Go
bazelisk build //samples/add_request_header:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/add_request_header/tests.textpb \
    --plugin /mnt/bazel-bin/samples/add_request_header/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/add_request_header:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **AddsRequestHeader** | Injects the new headers when they do not previously exist on the request. |
| **UpdatesRequestHeader** | Appends to the existing `Message` header and overwrites the existing `Welcome` header. |
| **RequestAndResponse** | Verifies that the modifications occur only on the request phase. |
| **CaseInsensitiveUpdates** | Properly updates existing headers regardless of their original case. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

