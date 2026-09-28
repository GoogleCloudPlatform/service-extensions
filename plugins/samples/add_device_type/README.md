# Device Type Detection Plugin

This plugin analyzes the `User-Agent` header of incoming HTTP requests and adds a new `x-device-type` header that categorizes the client device as `desktop`, `tablet`, `phone`, `bot`, or `other`. Use this plugin when you need to route traffic based on device type, serve device-specific content, implement adaptive layouts, or track analytics by device category. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.
2. The plugin reads the `User-Agent` header and converts it to lowercase for case-insensitive matching.
3. The plugin evaluates the user agent string against several keyword lists in priority order:
   - **Bot detection** (highest priority): Checks for keywords like `bot`, `crawler`, `spider`, `googlebot`, `bingbot`, etc.
   - **Tablet detection**: Checks for keywords like `ipad`, `tablet`, `kindle`, `nexus 7`, etc. For Android devices, requires additional indicators like `tablet`, `tab`, or `pad` to distinguish from phones.
   - **Phone detection**: Checks for keywords like `mobile`, `iphone`, `android`, `ipod`, `blackberry`, etc.
   - **Desktop detection**: Checks for browser keywords like `mozilla`, `chrome`, `safari`, `firefox`, `edge`, etc.
4. The plugin sets the `x-device-type` header to the detected category (`bot`, `tablet`, `phone`, `desktop`, or `other` if no match).
5. The plugin returns `Action::Continue`, forwarding the request with the new header to the upstream server.

## Implementation Notes

- **Normalization**: The user agent string is converted to lowercase for case-insensitive processing. C++ leverages `absl::AsciiStrToLower()`.
- **Detection Order**: Bot detection is executed first so bots aren't incorrectly categorized as device types.
- **Android distinction**: Differentiating an Android tablet from a phone requires matching additional indicators (like `tablet` or `pad`).
- **Data structures**: Keyword lists are stored efficiently as static/module-level variables or slices.

## Configuration

No configuration required. All device detection keywords are hardcoded as constants within the plugin source code. The keyword lists include common identifiers for:
- **Bots**: `bot`, `crawler`, `spider`, `googlebot`, `bingbot`, `slurp`, `duckduckbot`, `yandexbot`, `baiduspider`
- **Tablets**: `ipad`, `tablet`, `kindle`, `tab`, `playbook`, `nexus 7`, `sm-t`, `pad`, `gt-p`
- **Phones**: `mobile`, `android`, `iphone`, `ipod`, `blackberry`, `windows phone`, `webos`, `iemobile`, `opera mini`
- **Desktops**: `mozilla`, `chrome`, `safari`, `firefox`, `msie`, `opera`, `edge`, `chromium`, `vivaldi`

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/device_type:plugin_rust.wasm

# C++
bazelisk build //samples/device_type:plugin_cpp.wasm

# Go
bazelisk build //samples/device_type:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/device_type/tests.textpb \
    --plugin /mnt/bazel-bin/samples/device_type/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/device_type:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **DetectDesktopUserAgent** | Correctly identifies a Chrome on Windows browser as a desktop device. |
| **DetectIPhoneUserAgent** | Correctly identifies an iPhone as a mobile phone. |
| **DetectIPadUserAgent** | Correctly identifies an iPad as a tablet device. |
| **DetectAndroidPhoneUserAgent** | Correctly identifies an Android phone via the `mobile` keyword. |
| **DetectAndroidTabletUserAgent** | Correctly identifies an Android tablet via a specific model identifier keyword. |
| **DetectBotUserAgent** | Correctly identifies Googlebot as a bot. |
| **MissingUserAgent** | Defaults to the `other` category when the header is missing. |
| **CaseInsensitivity** | Successfully handles uppercase user agent strings. |
| **BenchmarkDetection** | Validates performance during normal desktop parsing. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
