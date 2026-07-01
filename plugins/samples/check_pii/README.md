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

## Implementation Notes

- **Regular expression compilation**: The regex is compiled once during plugin initialization (`onConfigure` or `NewPluginContext`) for optimal performance.
- **Conditional execution**: Processing is bypassed entirely unless the specific `google-run-pii-check` header is present and set to true.
- **Header sweeping**: The plugin iterates through all response headers, matching and masking credit card numbers in-place.
- **Body scanning**: The response body is fully read into a buffer, scanned against the regex pattern, and replaced if matches occur.

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

| Scenario | Description |
|---|---|
| **WithRunCheckHeaderOverwriteCardNumberOnResponseHeader** | Correctly masks credit card numbers in response headers when the check is enabled. |
| **WithoutRunCheckHeaderKeepTheOriginalHeaders** | Leaves response headers untouched when the PII check is disabled. |
| **WithRunCheckHeaderOverwriteCardNumberOnBody** | Correctly masks multiple credit card numbers within the response body when enabled. |
| **WithoutRunCheckHeaderKeepTheOriginalBody** | Leaves the response body untouched when the PII check is disabled. |

## Available Languages

- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
- [ ] Rust (not available)
