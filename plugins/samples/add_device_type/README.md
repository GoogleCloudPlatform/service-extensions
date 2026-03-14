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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Reads the `User-Agent` header, detects device type, and adds the `x-device-type` header |

## Key Code Walkthrough

The core logic is conceptually identical across all three language implementations:

- **User-Agent extraction** — The plugin reads the `user-agent` header:
  - **C++** uses `getRequestHeader("user-agent")` and `absl::AsciiStrToLower()` to normalize the string.
  - **Go** uses `proxywasm.GetHttpRequestHeader(userAgentHeader)` and `strings.ToLower()`. If the header is missing, it defaults to `"unknown"`.
  - **Rust** uses `self.get_http_request_header("user-agent")` with `unwrap_or_default()` and `.to_lowercase()`.

- **Device type detection** — The plugin evaluates the user agent in priority order using helper functions:
  - **`IsBot()`/`isBot()`/`is_bot()`** — Checks for bot/crawler keywords. Bots are detected first to prevent misclassification (e.g., a bot pretending to be a mobile device).
  - **`IsTablet()`/`isTablet()`/`is_tablet()`** — Checks for tablet keywords. For Android devices, requires additional indicators (`tablet`, `tab`, `pad`) because Android user agents can represent both phones and tablets.
  - **`IsMobile()`/`isMobile()`/`is_mobile()`** — Checks for mobile phone keywords like `iphone`, `android`, `mobile`.
  - **`IsDesktop()`/`isDesktop()`/`is_desktop()`** — Checks for desktop browser keywords like `chrome`, `firefox`, `safari`.
  - If no category matches, the device type is set to `other`.

- **Keyword matching** — All implementations use a `ContainsAny()` / `containsAny()` / `contains_any()` helper that checks if the user agent contains any keyword from a given list. Keywords are stored as static/package-level constants for efficiency:
  - **C++**: Static methods on `MyRootContext` return references to static vectors.
  - **Go**: Package-level `[]string` slices (`botKeywords`, `tabletKeywords`, etc.).
  - **Rust**: Static slices (`&[&str]`) defined inline in each detection function.

- **Header modification** — The plugin sets the `x-device-type` header:
  - **`replaceRequestHeader("x-device-type", device_type)`** (C++)
  - **`proxywasm.ReplaceHttpRequestHeader(deviceTypeHeader, deviceType)`** (Go)
  - **`self.set_http_request_header("x-device-type", Some(&device_type))`** (Rust)

The detection priority ensures that bots are never misclassified, and Android tablets are distinguished from Android phones.

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

| Scenario | Input | Output |
|---|---|---|
| **DetectDesktopUserAgent** | `User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36` | `x-device-type: desktop` (Chrome on Windows detected as desktop) |
| **DetectIPhoneUserAgent** | `User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1` | `x-device-type: phone` (iPhone detected as phone) |
| **DetectIPadUserAgent** | `User-Agent: Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1` | `x-device-type: tablet` (iPad detected as tablet) |
| **DetectAndroidPhoneUserAgent** | `User-Agent: Mozilla/5.0 (Linux; Android 10; SM-G960U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36` | `x-device-type: phone` (Android phone detected via `mobile` keyword) |
| **DetectAndroidTabletUserAgent** | `User-Agent: Mozilla/5.0 (Linux; Android 10; SM-T510) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Safari/537.36` | `x-device-type: tablet` (Android tablet detected via `SM-T` model identifier) |
| **DetectBotUserAgent** | `User-Agent: Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)` | `x-device-type: bot` (Googlebot detected as bot) |
| **MissingUserAgent** | No `User-Agent` header present | `x-device-type: other` (missing user agent defaults to `other`) |
| **CaseInsensitivity** | `User-Agent: MOZILLA/5.0 (IPHONE; CPU iPhone OS)` (uppercase) | `x-device-type: phone` (case-insensitive matching detects iPhone) |
| **BenchmarkDetection** | `User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36` | `x-device-type: desktop` (performance benchmark test) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
