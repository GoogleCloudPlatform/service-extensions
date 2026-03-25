# Add Custom Response Plugin

This plugin intercepts 5xx server error responses and replaces them with a 302 redirect to a custom error page. It preserves the original status code in a custom header (`Origin-Status`) for debugging purposes. Use this plugin when you need to provide a user-friendly error page for server errors, improve user experience during outages, or centralize error handling across multiple backend services. It operates during the **response headers** processing phase.

## How It Works

1. The proxy receives an HTTP response from the upstream server and invokes the plugin's `on_http_response_headers` callback.
2. The plugin reads the `:status` pseudo-header and parses it as an integer.
3. If the status code is in the 5xx range (500-599), the plugin calls `send_http_response` to generate a new 302 (Found) redirect response.
4. The redirect response includes:
   - `Location` header pointing to a custom error page (`https://storage.googleapis.com/www.example.com/server-error.html`)
   - `Origin-Status` header containing the original 5xx status code for logging/debugging
5. The plugin returns `Action::Continue`, and the proxy sends the redirect response to the client instead of the original 5xx error.

## Implementation Notes

- **Status parsing**: The plugin extracts the `:status` pseudo-header; C++ uses `absl::SimpleAtoi()`.
- **Redirect generation**: A 302 redirect is sent directly from the plugin instead of returning the upstream response. C++ requires returning `FilterHeadersStatus::ContinueAndEndStream` after sending the local response to halt the original response body.
- **Diagnostic headers**: The original status code is preserved in the custom `Origin-Status` header.
- **Redirection URL**: The destination error page is hardcoded as a constant string.

## Configuration

No configuration required. The redirect URL is hardcoded as a constant:
- **C++**: `redirect_page = "https://storage.googleapis.com/www.example.com/server-error.html"`
- **Go**: `redirectPage = "https://storage.googleapis.com/www.example.com/server-error.html"`
- **Rust**: `REDIRECT_PAGE = "https://storage.googleapis.com/www.example.com/server-error.html"`

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/add_custom_response:plugin_rust.wasm

# C++
bazelisk build //samples/add_custom_response:plugin_cpp.wasm

# Go
bazelisk build //samples/add_custom_response:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/add_custom_response/tests.textpb \
    --plugin /mnt/bazel-bin/samples/add_custom_response/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/add_custom_response:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **NoRedirect** | Does nothing for successful responses. |
| **DoRedirect** | Intercepts a 5xx response and redirects the client to the custom error page while preserving the original status code. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
