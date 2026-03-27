# Normalize Header Plugin

This plugin detects the client's device type by analyzing request headers and adds a normalized `client-device-type` header with the detected value. It uses a priority-based detection strategy, first checking the modern Client Hints API (`Sec-CH-UA-Mobile`) and falling back to User-Agent string analysis. Use this plugin when you need to route mobile vs. desktop traffic differently, apply device-specific rate limits, or enable backend services to make device-aware decisions without complex User-Agent parsing. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. **Priority-based device detection** (in order):

   **Priority 1 - Client Hints API (`Sec-CH-UA-Mobile` header)**:
   - The plugin checks if the `Sec-CH-UA-Mobile` header is present and equals `"?1"` (indicating a mobile device).
   - If true, the plugin adds `client-device-type: mobile` and returns immediately.
   - This is the most reliable method as it's standardized and cannot be easily spoofed.

   **Priority 2 - User-Agent analysis**:
   - If Client Hints are not available, the plugin checks the `User-Agent` header for the substring `"mobile"` (case-insensitive).
   - If found, the plugin adds `client-device-type: mobile` and returns.

   **Default - Unknown device**:
   - If neither detection method identifies a mobile device, the plugin adds `client-device-type: unknown`.

3. The plugin always adds exactly one `client-device-type` header and returns `Continue` / `ActionContinue`, allowing the request to proceed to the upstream server.

## Implementation Notes

- **Client Hints prioritization**: Prefers the modern, standardized `Sec-CH-UA-Mobile` header to accurately identify mobile devices over fragile user-agent heuristics.
- **User-Agent fallback**: Falls back to case-insensitive `User-Agent` substring searching if client hints are unavailable.
- **Early termination**: Emits the normalized header and returns `Continue` immediately after the first successful strategy matches, skipping redundant checks.

## Configuration

No configuration required. The header name (`client-device-type`) and detection logic are hardcoded in the plugin source.

To customize:
- **Header name**: Change `"client-device-type"` (Rust uses `DEVICE_TYPE_KEY` constant)
- **Device values**: Change `"mobile"` and `"unknown"` (Rust uses `DEVICE_TYPE_VALUE` constant)
- **Detection logic**: Add more header checks or User-Agent patterns

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/normalize_header:plugin_rust.wasm

# C++
bazelisk build //samples/normalize_header:plugin_cpp.wasm

# Go
bazelisk build //samples/normalize_header:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/normalize_header/tests.textpb \
    --plugin /mnt/bazel-bin/samples/normalize_header/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/normalize_header:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **NoHeaderSet** | Assigns the device type as `unknown` when no indicators are present. |
| **WithMobileHeaderHintEqTrue** | Accurately identifies a mobile device via the `Sec-CH-UA-Mobile` indicator, bypassing the user agent check. |
| **WithMobileHeaderHintEqFalse** | Correctly identifies a non-mobile device when the hint explicitly denies it, despite lack of user agent substrings. |
| **WithMobileUserAgent** | Accurately identifies a mobile device by correctly parsing the user agent fallback. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
