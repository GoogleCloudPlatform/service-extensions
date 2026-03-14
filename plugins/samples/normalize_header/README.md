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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Detects device type from headers and adds normalized `client-device-type` header |

## Key Code Walkthrough

The core logic is identical across all three language implementations:

- **Client Hints detection** — The plugin checks the standardized mobile hint:
  - **C++**:
    ```cpp
    const auto mobile_header = getRequestHeader("Sec-CH-UA-Mobile");
    if (mobile_header && mobile_header->view() == "?1") {
        addRequestHeader("client-device-type", "mobile");
        return FilterHeadersStatus::Continue;
    }
    ```
  
  - **Go**:
    ```go
    mobileHeader, err := proxywasm.GetHttpRequestHeader("Sec-CH-UA-Mobile")
    if err == nil && mobileHeader == "?1" {
        proxywasm.AddHttpRequestHeader("client-device-type", "mobile")
        return types.ActionContinue
    }
    ```
  
  - **Rust**:
    ```rust
    let mobile_header = self.get_http_request_header("Sec-CH-UA-Mobile");
    if mobile_header.unwrap_or_default() == "?1" {
        self.add_http_request_header(DEVICE_TYPE_KEY, DEVICE_TYPE_VALUE);
        return Action::Continue;
    }
    ```

  The value `"?1"` is the standard boolean-true representation in structured headers (RFC 8941).

- **User-Agent fallback** — The plugin performs case-insensitive substring matching:
  - **C++**:
    ```cpp
    const auto user_agent = getRequestHeader("User-Agent");
    if (user_agent && absl::StrContainsIgnoreCase(user_agent->view(), "mobile")) {
        addRequestHeader("client-device-type", "mobile");
        return FilterHeadersStatus::Continue;
    }
    ```
    Uses Abseil's `StrContainsIgnoreCase` for efficient case-insensitive search.

  - **Go**:
    ```go
    userAgentHeader, err := proxywasm.GetHttpRequestHeader("User-Agent")
    if err == nil && strings.Contains(strings.ToLower(userAgentHeader), "mobile") {
        proxywasm.AddHttpRequestHeader("client-device-type", "mobile")
        return types.ActionContinue
    }
    ```
    Converts to lowercase before checking for substring.

  - **Rust**:
    ```rust
    let user_agent = self.get_http_request_header("User-Agent");
    if user_agent.map_or(false, |s| s.to_lowercase().contains(DEVICE_TYPE_VALUE)) {
        self.add_http_request_header(DEVICE_TYPE_KEY, DEVICE_TYPE_VALUE);
        return Action::Continue;
    }
    ```
    Uses `map_or` to handle `Option` and converts to lowercase.

- **Default value** — If no mobile indicators are found:
  - All implementations add `client-device-type: unknown` as the fallback value.

- **Early return pattern** — All implementations use early returns after each detection method succeeds, ensuring only one header is added and avoiding unnecessary checks.

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

| Scenario | Input | Output |
|---|---|---|
| **NoHeaderSet** | No `Sec-CH-UA-Mobile` or `User-Agent` headers | `client-device-type: unknown` (default value) |
| **WithMobileHeaderHintEqTrue** | `Sec-CH-UA-Mobile: ?1`, `User-Agent: Chrome...` | `client-device-type: mobile` (Client Hints has priority) |
| **WithMobileHeaderHintEqFalse** | `Sec-CH-UA-Mobile: ?0`, `User-Agent: Chrome...` | `client-device-type: unknown` (Client Hints explicitly says not mobile; User-Agent doesn't contain "mobile") |
| **WithMobileUserAgent** | `User-Agent: Chrome/... Mobile/...` | `client-device-type: mobile` (User-Agent contains "mobile" substring) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
