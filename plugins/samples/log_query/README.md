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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Parses the `:path` header, extracts the `token` query parameter, and logs its value |

## Key Code Walkthrough

The core logic is conceptually identical across all three language implementations:

- **Path retrieval** — The plugin reads the `:path` header:
  - **C++**: `WasmDataPtr path = getRequestHeader(":path");`
  - **Go**: `path, err := proxywasm.GetHttpRequestHeader(":path")`
  - **Rust**: `self.get_http_request_header(":path")`

- **URL parsing** — Each language uses its standard URL parsing library:
  - **C++**:
    ```cpp
    boost::system::result<boost::urls::url_view> url =
        boost::urls::parse_uri_reference(path->view());
    auto it = url->params().find("token");
    if (it != url->params().end()) {
        token = (*it).value;
    }
    ```
    Boost.URL automatically handles URL decoding of parameter values.

  - **Go**:
    ```go
    u, err := url.Parse(path)
    token := u.Query().Get("token")
    if token == "" {
        token = "<missing>"
    }
    ```
    The `Query().Get()` method automatically handles URL decoding.

  - **Rust**:
    ```rust
    let base = Url::parse("http://example.com").ok();
    let options = Url::options().base_url(base.as_ref());
    let token: Option<String> = match options.parse(&path) {
        Ok(url) => url.query_pairs().find_map(|(k, v)| {
            if k == "token" {
                Some(v.to_string())
            } else {
                None
            }
        }),
        Err(_) => None,
    };
    ```
    Rust requires a base URL to parse relative paths. The `query_pairs()` iterator automatically handles URL decoding.

- **Error handling** — Each language handles parsing errors differently:
  - **C++**: Returns `"<missing>"` if URL parsing fails or parameter is not found.
  - **Go**: Uses `defer recover()` to catch panics from parsing errors and sends a 500 response.
  - **Rust**: Returns `None` if URL parsing fails, which is converted to `"<missing>"` by `unwrap_or()`.

- **Logging** — The token value is logged:
  - **C++**: `LOG_INFO("token: " + token);`
  - **Go**: `proxywasm.LogInfof("token: %s", token);`
  - **Rust**: `info!("token: {}", token.unwrap_or("<missing>".to_string()));`

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

| Scenario | Input | Output |
|---|---|---|
| **NoPath** | No `:path` header | No log output (path is missing) |
| **NoToken** | `:path: /foo?bar=baz&a=b` (no `token` parameter) | Log: `token: <missing>` |
| **LogToken** | `:path: /foo?bar=baz&token=so%20special&a=b` (URL-encoded token) | Log: `token: so special` (URL-decoded value) |

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
