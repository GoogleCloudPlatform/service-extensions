# Log Query Plugin

This plugin demonstrates how to parse URL query parameters from HTTP requests and log specific values. It extracts the `token` query parameter from the request path, handles URL decoding, and logs the value (or `"<missing>"` if not present). Use this plugin when you need to extract and log query parameters for debugging, implement parameter-based logic, or learn URL parsing in Proxy-WASM. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. The plugin reads the `:path` pseudo-header, which contains the request path including query parameters (e.g., `/foo?bar=baz&token=value&a=b`).

3. **URL parsing**: The plugin parses the path as a URL:
   - **C++** uses Boost.URL's `parse_uri_reference()` to parse the path as a relative URL reference.
   - **Go** uses `url.Parse()` from the standard library.
   - **Rust** uses the `url` crate with a dummy base URL (`http://example.com`) to parse relative paths.

4. **Parameter extraction**: The plugin searches for the `token` query parameter:
   - If found, the value is extracted and URL-decoded (e.g., `so%20special` becomes `so special`).
   - If not found, the string `"<missing>"` is used.

5. **Logging**: The plugin logs the token value using the appropriate logging mechanism:
   - **C++**: `LOG_INFO("token: " + token)`
   - **Go**: `proxywasm.LogInfof("token: %s", token)`
   - **Rust**: `info!("token: {}", token)`

6. The plugin returns `Continue` / `ActionContinue`, allowing the request to proceed normally to the upstream server.

## Implementation Notes

- **Path retrieval**: Extracts the raw HTTP path string via the `:path` pseudo-header.
- **URL parsing**: Leverages standard URL libraries across languages (`Boost.URL` in C++, `net/url` in Go, `url` crate in Rust) to safely decode and parse query parameters.
- **Fallback behaviors**: Gracefully handles missing token parameters by emitting a `<missing>` string rather than triggering errors.

## Configuration

No configuration required.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/log_query:plugin_rust.wasm

# C++
bazelisk build //samples/log_query:plugin_cpp.wasm

# Go
bazelisk build //samples/log_query:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/log_query/tests.textpb \
    --plugin /mnt/bazel-bin/samples/log_query/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/log_query:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **NoPath** | Does not log anything when the `:path` pseudo-header is completely missing. |
| **NoToken** | Logs a missing status when the expected `token` parameter is not present in the URL. |
| **LogToken** | Correctly parses, URL-decodes, and logs the value of the provided `token`. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Use Cases

- **Debugging**: Log specific query parameters for troubleshooting.
- **Parameter extraction**: Extract tokens, API keys, or other parameters for processing.
- **Conditional logic**: Make routing or authentication decisions based on query parameters.
- **Analytics**: Track usage of specific parameter values.
- **Learning tool**: Understand URL parsing APIs in Proxy-WASM environments.
