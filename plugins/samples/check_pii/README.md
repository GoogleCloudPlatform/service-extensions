# Check PII Plugin

This plugin detects and masks credit card numbers in HTTP response headers and bodies to prevent accidental exposure of personally identifiable information (PII). It uses regular expressions to find credit card numbers in a 19-character hyphenated format (e.g., `1234-5678-9123-4567`) and masks the first 12 digits while preserving the last 4 digits (e.g., `XXXX-XXXX-XXXX-4567`). The plugin only activates when the response includes a `google-run-pii-check: true` header. Use this plugin when you need to sanitize sensitive data in responses, implement data loss prevention (DLP), or ensure compliance with privacy regulations. It operates during the **response headers** and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP response from the upstream server and invokes the plugin's `on_http_response_headers` callback.
2. The plugin checks if the `google-run-pii-check` header is present and set to `"true"`.
3. If PII checking is enabled:
   - The plugin scans all response headers for credit card numbers matching the pattern `\d{4}-\d{4}-\d{4}-(\d{4})`.
   - For each match, the plugin replaces the first 12 digits with `XXXX-XXXX-XXXX-` while preserving the last 4 digits.
   - The plugin sets an internal flag (`check_body_`) to indicate that the response body should also be checked.
4. When the response body arrives, the plugin invokes `on_http_response_body`:
   - If the `check_body_` flag is set, the plugin scans the entire body for credit card numbers.
   - The plugin applies the same masking pattern, replacing matched numbers with `XXXX-XXXX-XXXX-[last 4 digits]`.
5. The plugin returns `Action::Continue`, forwarding the sanitized response to the client.

**Important limitation**: For simplicity, this plugin does not handle credit card numbers that are split across multiple `on_http_response_body` calls (chunk boundaries). In production, you would need to implement buffering or stateful pattern matching to handle this edge case.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_configure` | Compiles the credit card regex pattern once at plugin initialization (C++ only; Go compiles in `NewPluginContext`) |
| `on_http_response_headers` | Checks the `google-run-pii-check` header and masks credit card numbers in all response headers |
| `on_http_response_body` | Masks credit card numbers in the response body if PII checking is enabled |

## Key Code Walkthrough

The core logic is conceptually identical between the C++ and Go implementations:

- **Regex compilation** — The credit card pattern is compiled once to avoid repeated expensive operations:
  - **C++** compiles the regex in `onConfigure()` (root context) using `re2::RE2("\\d{4}-\\d{4}-\\d{4}-(\\d{4})")` and stores it in the root context (`card_match`). The HTTP context accesses it via `root_->card_match`.
  - **Go** compiles the regex in `NewPluginContext()` using `regexp.MustCompile("\\d{4}-\\d{4}-\\d{4}-(\\d{4})")` and stores it in the plugin context. The HTTP context receives a reference to the compiled regex.

  The pattern `\d{4}-\d{4}-\d{4}-(\d{4})` matches 19-character hyphenated credit card numbers and captures the last 4 digits in a group.

- **Conditional activation** — The plugin only processes responses with `google-run-pii-check: true`:
  - **C++** uses `getResponseHeader("google-run-pii-check")` and checks if `pii_header->view() == "true"`.
  - **Go** uses `proxywasm.GetHttpResponseHeader("google-run-pii-check")` and checks if `value != "true"` (inverted logic, returns early if not `"true"`).

- **Header scanning** — The plugin iterates through all response headers:
  - **C++** uses `getResponseHeaderPairs()->pairs()` to retrieve all headers, applies `maskCardNumbers()` to each value, and calls `replaceResponseHeader()` if a match is found.
  - **Go** uses `proxywasm.GetHttpResponseHeaders()` to retrieve all headers, applies `creditCardRegex.ReplaceAllString()` to each value, and calls `proxywasm.ReplaceHttpResponseHeader()` if the value changed.

- **Body scanning** — The plugin scans the response body if PII checking is enabled:
  - **C++** uses `getBufferBytes(WasmBufferType::HttpResponseBody, 0, body_buffer_length)` to read the entire body, applies `maskCardNumbers()`, and calls `setBuffer()` to replace the body if matches are found.
  - **Go** uses `proxywasm.GetHttpResponseBody(0, numBytes)` to read the body, applies `creditCardRegex.ReplaceAll()`, and calls `proxywasm.ReplaceHttpResponseBody()` to replace the body.

- **Masking pattern** — Both implementations replace matched credit card numbers with `XXXX-XXXX-XXXX-[last 4 digits]`:
  - **C++** uses `re2::RE2::GlobalReplace(&value, *root_->card_match, "XXXX-XXXX-XXXX-\\1")` where `\\1` references the captured last 4 digits.
  - **Go** uses `creditCardRegex.ReplaceAllString(value, "XXXX-XXXX-XXXX-${1}")` where `${1}` references the captured last 4 digits.

## Configuration

No configuration required. The credit card regex pattern and activation header (`google-run-pii-check`) are hardcoded in the plugin source.

**Credit card pattern**: `\d{4}-\d{4}-\d{4}-(\d{4})` (19 characters with hyphens)  
**Activation header**: `google-run-pii-check: true`

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/check_pii:plugin_cpp.wasm

# Go
bazelisk build //samples/check_pii:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/check_pii/tests.textpb \
    --plugin /mnt/bazel-bin/samples/check_pii/plugin_cpp.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/check_pii:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **WithRunCheckHeaderOverwriteCardNumberOnResponseHeader** | Response headers: `x-card-number: 1234-5678-9123-4567`, `google-run-pii-check: true` | `x-card-number: XXXX-XXXX-XXXX-4567` (credit card number masked in header) |
| **WithoutRunCheckHeaderKeepTheOriginalHeaders** | Response headers: `x-card-number: 1234-5678-9123-4567`, `google-run-pii-check: false` | `x-card-number: 1234-5678-9123-4567` (no masking, PII check disabled) |
| **WithRunCheckHeaderOverwriteCardNumberOnBody** | Response header: `google-run-pii-check: true`; Response body contains `1234-5678-9123-4567` and `1234-4567-9123-8886` | Body with credit card numbers masked: `XXXX-XXXX-XXXX-4567` and `XXXX-XXXX-XXXX-8886` |
| **WithoutRunCheckHeaderKeepTheOriginalBody** | Response header: `google-run-pii-check: false`; Response body contains `1234-5678-9123-4567` and `1234-4567-9123-8886` | Body unchanged (no masking, PII check disabled) |

## Available Languages

- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
- [ ] Rust (not available)
