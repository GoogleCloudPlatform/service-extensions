# Check PII Plugin

This plugin detects and masks sensitive numbers such as credit card numbers and 10-digit numeric codes in HTTP response headers and bodies to prevent accidental exposure of personally identifiable information (PII). It uses regular expressions to find credit card numbers in a 19-character hyphenated format (e.g., `1234-5678-9123-4567`) and masks the first 12 digits while preserving the last 4 digits (e.g., `XXXX-XXXX-XXXX-4567`). Additionally, it detects 10-digit codes and masks the first 7 digits (e.g., `XXXXXXX123`). Use this plugin when you need to sanitize sensitive data in responses, implement data loss prevention (DLP), or ensure compliance with privacy regulations. It operates during the **request headers**, **response headers**, and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_http_request_headers` callback.
   - The plugin forces uncompressed responses by changing the `Accept-Encoding` header to `identity`, as compressed bodies cannot be regex-matched directly.
2. The proxy receives the HTTP response from the upstream server and invokes the plugin's `on_http_response_headers`.
   - The plugin scans all response headers for credit card numbers and 10-digit codes.
   - For each match, the plugin replaces the first digits appropriately.
3. When the response body arrives, the plugin invokes `on_http_response_body`:
   - The plugin scans the response body chunks.
   - It applies the same masking patterns, replacing matched numbers while preserving the final digits.
4. The plugin returns `Action::Continue`, forwarding the sanitized response to the client.

**Important limitation**: For simplicity, this plugin does not handle credit card numbers or codes that are split across multiple `on_http_response_body` calls (chunk boundaries). It also prevents response compression to allow body scanning. In production, you would need to implement buffering or stateful pattern matching to handle chunking, and possibly decompress/recompress payloads.

## Implementation Notes

- **Regular expression compilation**: The regex patterns are compiled once during plugin initialization (`onConfigure` or `NewPluginContext`) for optimal performance.
- **Header sweeping**: The plugin iterates through all response headers, matching and masking data in-place.
- **Body scanning**: The response body bytes are loaded as strings, scanned against the regex patterns, and replaced if matches occur.
- **Compression handling**: Overwrites `Accept-Encoding` on requests to guarantee plaintext responses from backend.

## Configuration

No configuration required. The regex patterns are hardcoded in the plugin source.

**Credit card pattern**: `\d{4}-\d{4}-\d{4}-(\d{4})` (19 characters with hyphens)  
**10-Digit Code pattern**: `\d{7}(\d{3})`

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

| Scenario | Description |
|---|---|
| **OverwriteCardNumberOnResponseHeader** | Correctly masks credit card numbers found in response headers. |
| **OverwriteCardNumberOnBody** | Correctly masks multiple credit card numbers within the response body. |
| **Overwrite10DigitCodeOnResponseHeader** | Correctly masks 10-digit codes found in response headers. |
| **Overwrite10DigitCodeOnResponseBody** | Correctly masks 10-digit codes within the response body. |
| **OverwritePIIOnResponseBody** | Masks both 10-digit codes and credit card formats correctly within the body. |
| **OverwriteMultiplePIIInHeadersAndBody** | Successfully masks multiple variations of PII data across both headers and bodies. |
| **EnsureNonPIIDataRemainsUnchanged** | Leaves headers and body text untouched that do not match the PII formats. |
| **OverwriteMultiple10DigitCodesInBody** | Handles multiple consecutive 10-digit code instances in the same body content. |
| **Overwrite10DigitCodesAdjacentToOtherCharacters** | Masks 10-digit codes correctly even when they adjoin text characters. |
| **OverwritePIIDataAdjacentToOtherCharacters** | Masks credit card formats correctly even when they adjoin text characters. |
| **OverwriteAcceptEncodingRequestHeader** | Intercepts the request and sets `Accept-Encoding` header to `identity`. |

## Available Languages

- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
- [ ] Rust (not available)
