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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_response_headers` | Inspects the `:status` header and sends a 302 redirect for 5xx responses |

## Key Code Walkthrough

The core logic is identical across all three language implementations:

- **Status code extraction and parsing** — The plugin reads the `:status` pseudo-header:
  - **C++** uses `getResponseHeader(":status")` and `absl::SimpleAtoi()` to parse the value.
  - **Go** uses `proxywasm.GetHttpResponseHeader(":status")` and `strconv.Atoi()`.
  - **Rust** uses `self.get_http_response_header(":status")` and `status.parse::<u16>()`.

- **5xx detection** — The plugin checks if `response_code / 100 == 5` (integer division), which matches any status code from 500 to 599.

- **Custom redirect response** — If a 5xx is detected, the plugin generates a 302 redirect:
  - **`sendLocalResponse(302, "", "", {{"Origin-Status", ...}, {"Location", ...}})`** (C++)
  - **`proxywasm.SendHttpResponse(302, [][2]string{{"Origin-Status", ...}, {"Location", ...}}, nil, 0)`** (Go)
  - **`self.send_http_response(302, vec![("Origin-Status", ...), ("Location", ...)], None)`** (Rust)
  
  The `Origin-Status` header preserves the original error code (e.g., `501`, `503`) for diagnostic purposes, while `Location` directs the client to the custom error page.

- **Return value** — C++ returns `FilterHeadersStatus::ContinueAndEndStream` after sending the redirect to signal the proxy should not forward the original response body. Go and Rust return `Action::Continue`, as the redirect response replaces the original response entirely.

The redirect page URL is hardcoded as a constant: `https://storage.googleapis.com/www.example.com/server-error.html`.

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

| Scenario | Input | Output |
|---|---|---|
| **NoRedirect** | Response with `:status: 200` | `:status: 200` unchanged, no `Location` header (non-5xx response passes through) |
| **DoRedirect** | Response with `:status: 501` | 302 redirect with `Location: https://storage.googleapis.com/www.example.com/server-error.html` and `Origin-Status: 501` (original 5xx replaced with redirect) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
