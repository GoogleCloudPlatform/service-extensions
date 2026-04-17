# Error Page with Trace ID Plugin

This plugin generates custom HTML error pages for 4xx and 5xx responses, embedding the request's trace ID for debugging and support purposes. It extracts trace IDs from standard distributed tracing headers (Google Cloud Trace Context or W3C Trace Context) and displays them in a user-friendly error page. Use this plugin when you need to provide branded error pages with troubleshooting information, enable support teams to correlate user reports with backend logs, or improve user experience during errors while maintaining observability. It operates during the **request headers** and **response headers** processing phases.

## How It Works

1. **Request processing**: When the proxy receives an HTTP request, it invokes `on_http_request_headers`:
   - The plugin extracts the trace ID from distributed tracing headers in order of precedence:
     1. **`x-cloud-trace-context`** (Google Cloud format): `TRACE_ID/SPAN_ID;o=TRACE_TRUE` → extracts `TRACE_ID`
     2. **`traceparent`** (W3C Trace Context format): `00-TRACE_ID-SPAN_ID-FLAGS` → extracts `TRACE_ID` (32 hex digits)
   - The plugin stores the trace ID in the HTTP context for later use. If no trace header is present, it defaults to `"not-available"`.
   - The plugin logs the captured trace ID at the debug level.

2. **Response processing**: When the proxy receives a response, it invokes `on_http_response_headers`:
   - The plugin reads the `:status` pseudo-header and parses it as an integer.
   - If the status code is less than 400 (2xx or 3xx), the plugin allows the response to pass through unmodified.
   - If the status code is 400 or greater (4xx or 5xx), the plugin generates a custom HTML error page:
     - The plugin replaces placeholders in the `kErrorTemplate` with the actual status code and trace ID.
     - The plugin sends the custom error page using `sendLocalResponse()` with the original status code and `Content-Type: text/html; charset=utf-8`.
   - The plugin returns `FilterHeadersStatus::StopIteration` to prevent the original error response from being forwarded.

3. **Trace ID extraction**: The plugin uses a precompiled regex (compiled in `on_configure`) to parse W3C Trace Context headers and validate the format.

## Implementation Notes

- **Regex compilation**: Compiles a regex for W3C trace validation once during plugin initialization.
- **Trace ID extraction**: Extracts trace components from `x-cloud-trace-context` or `traceparent` headers with defined precedence rule logic.
- **Template injection**: Replaces status code and trace ID placeholders within a hardcoded HTML string template using `absl::StrReplaceAll`.
- **Response replacement**: Intercepts 4xx/5xx responses and replaces them completely with a custom localized HTML response, halting further upstream error propagation.

## Configuration

No configuration required. The error page template and trace header names are hardcoded in the plugin source.

## Build

Build the plugin for C++ from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/error_page_with_traceid:plugin_cpp.wasm
```

**Note**: Only C++ implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/error_page_with_traceid/tests.textpb \
    --plugin /mnt/bazel-bin/samples/error_page_with_traceid/plugin_cpp.wasm

# Using Bazel
bazelisk test --test_output=all //samples/error_page_with_traceid:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **ErrorPage502Status** | Properly generates a custom error page embedding the expected trace context for a 502 status. |
| **NoErrorPageFor200** | Permits 200 OK responses to pass unmodified. |
| **ErrorPagePreservesContentType** | Intercepts a 500 error, replacing headers and JSON body with the HTML template containing the W3C trace ID. |
| **MultipleDifferentTraceHeaders** | Prioritizes the Google Cloud trace ID when both formats are present. |
| **GoogleTraceWithoutSpan** | Utilizes the entire trace context string when a valid Google Cloud separation character is missing. |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
