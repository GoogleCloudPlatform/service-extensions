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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Adds the `Message` header and sets the `Welcome` header on every incoming request |

## Key Code Walkthrough

The core logic is identical across all three language implementations:

- **`add_http_request_header("Message", "hello")`** — Appends the value `hello`
  to the `Message` header. If the header doesn't exist, it is created. If it
  already exists, the value is appended with a comma separator (e.g.,
  `hey, hello`). This is the **add** semantic.

- **`set_http_request_header("Welcome", "warm")`** (Rust) /
  **`replaceRequestHeader("Welcome", "warm")`** (C++) /
  **`ReplaceHttpRequestHeader("Welcome", "warm")`** (Go) — Overwrites the
  `Welcome` header with `warm`, regardless of any existing value. This is the
  **set/replace** semantic.

The distinction between add and set/replace is a fundamental concept in header
manipulation. This sample is a good starting point for understanding how each
operation behaves, especially with pre-existing headers.

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

| Scenario | Input | Output |
|---|---|---|
| **AddsRequestHeader** | Request with no `Message` or `Welcome` headers | `Message: hello`, `Welcome: warm` added |
| **UpdatesRequestHeader** | Request with `Message: hey` and `Welcome: cold` | `Message: hey, hello` (appended), `Welcome: warm` (replaced) |
| **RequestAndResponse** | Request with no `Message` header | `Message: hello` added (response path is unaffected) |
| **CaseInsensitiveUpdates** | Request with `message: hey` and `welcome: cold` (lowercase) | `message: hey, hello` (appended), `welcome: warm` (replaced) — header names are case-insensitive |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

