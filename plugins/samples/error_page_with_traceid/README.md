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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_configure` | Compiles the W3C Trace Context regex pattern at plugin initialization for efficient trace ID extraction |
| `on_http_request_headers` | Extracts and stores the trace ID from `x-cloud-trace-context` or `traceparent` headers |
| `on_http_response_headers` | Checks response status code and generates custom HTML error page for 4xx/5xx responses with embedded trace ID |

## Key Code Walkthrough

This plugin is only available in C++:

- **HTML template** — The plugin defines a custom error page template as a raw string literal:
  ```cpp
  constexpr std::string_view kErrorTemplate = R"(
  <html>
  <head>
    <title>Error {STATUS_CODE}</title>
    <style>...</style>
  </head>
  <body>
    <div class="container">
      <h1>Error {STATUS_CODE}</h1>
      <p>We're sorry, something went wrong with your request.</p>
      <div class="trace-id">
        <strong>Trace ID:</strong> {TRACE_ID}
      </div>
      <p>Please provide this trace ID to support for assistance.</p>
    </div>
  </body>
  </html>
  )";
  ```
  The template includes placeholders `{STATUS_CODE}` and `{TRACE_ID}` that are replaced at runtime.

- **Regex compilation** — In `on_configure()`, the plugin compiles a regex to validate and extract trace IDs from W3C Trace Context headers:
  ```cpp
  w3c_trace_regex_ = std::make_unique<re2::RE2>(
      R"(^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$)", 
      re2::RE2::Quiet);
  ```
  The pattern matches the W3C format `00-<32 hex trace ID>-<16 hex span ID>-<2 hex flags>` and captures the trace ID.

- **Trace ID extraction** — The `extractTraceId()` method implements precedence-based extraction:
  1. **Google Cloud Trace Context** (`x-cloud-trace-context`):
     ```cpp
     // Format: TRACE_ID/SPAN_ID;o=TRACE_TRUE
     const size_t slash_pos = trace_context.find('/');
     if (slash_pos != std::string::npos) {
         return trace_context.substr(0, slash_pos);
     }
     ```
     The plugin extracts the substring before the `/` character.

  2. **W3C Trace Context** (`traceparent`):
     ```cpp
     if (re2::RE2::FullMatch(trace_context, *root_->w3c_trace_regex_, &trace_id)) {
         return trace_id;
     }
     ```
     The plugin uses the precompiled regex to validate and extract the trace ID.

  3. **Fallback**: If no trace header is present or the format is invalid, the method returns `"not-available"`.

- **Error page generation** — In `on_http_response_headers()`, the plugin checks the status code:
  ```cpp
  if (status_code < 400) return FilterHeadersStatus::Continue;
  
  std::string error_page = std::string(kErrorTemplate);
  error_page = absl::StrReplaceAll(error_page, {
      {"{STATUS_CODE}", status_code_},
      {"{TRACE_ID}", trace_id_}
  });
  
  sendLocalResponse(
      status_code,
      "",
      error_page,
      {{"Content-Type", "text/html; charset=utf-8"}}
  );
  ```
  The plugin uses `absl::StrReplaceAll()` to replace all occurrences of the placeholders in a single pass.

- **Status code preservation** — The plugin preserves the original HTTP status code (e.g., 404, 500, 502) in the custom error page response.

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

| Scenario | Input | Output |
|---|---|---|
| **ErrorPage502Status** | Request with `x-cloud-trace-context: abcdef123456789`; Response with `:status: 502` | 502 response with custom HTML containing `"Error 502"` and `"abcdef123456789"` |
| **NoErrorPageFor200** | Request with `x-cloud-trace-context: abcdef123456789`; Response with `:status: 200` | Response passes through unmodified (no custom error page for 2xx status) |
| **ErrorPagePreservesContentType** | Request with `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`; Response with `:status: 500`, `content-type: application/json`, `x-custom-header: test-value` | 500 response with custom HTML containing `"Error 500"` and W3C trace ID `"4bf92f3577b34da6a3ce929d0e0e4736"` (original response headers replaced) |
| **MultipleDifferentTraceHeaders** | Request with both `x-cloud-trace-context: cloud-trace-id/1` and `traceparent: 00-w3c-trace-id-00f067aa0ba902b7-01`; Response with `:status: 429` | 429 response with custom HTML containing Google Cloud trace ID `"cloud-trace-id"` (Google Cloud header takes precedence) |
| **GoogleTraceWithoutSpan** | Request with `x-cloud-trace-context: trace-without-span-id` (no `/` separator); Response with `:status: 500` | 500 response with custom HTML containing full trace context `"trace-without-span-id"` (entire header value used when no span separator found) |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
