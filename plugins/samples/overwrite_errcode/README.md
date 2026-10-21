# Overwrite Error Code Plugin

This plugin demonstrates response status code manipulation by remapping server errors (5xx status codes) to a different status code. It intercepts all 5xx responses (500, 502, 503, etc.) and changes them to 404 Not Found. Use this plugin when you need to hide internal server errors from clients, normalize error responses, or implement custom error mapping strategies for security or UX reasons. It operates during the **response headers** processing phase.

## How It Works

1. The proxy receives an HTTP response from the upstream server and invokes the plugin's `on_http_response_headers` callback.

2. **Status code extraction**: The plugin reads the `:status` pseudo-header and parses it as an integer.

3. **5xx detection**: The plugin checks if the status code is in the 5xx range by dividing by 100:
   - `response_code / 100 == 5` matches 500-599

4. **Status code remapping**: If a 5xx status is detected:
   - The plugin calls `mapResponseCode()` (C++/Go) or directly sets `"404"` (Rust)
   - The remapping function returns 404 for all 5xx codes
   - The plugin replaces the `:status` header with the new value

5. **Non-5xx responses**: For all other status codes (2xx, 3xx, 4xx), the response passes through unchanged.

6. The plugin returns `Continue` / `ActionContinue`, forwarding the (potentially modified) response to the client.

## Implementation Notes

- **Status code parsing**: Safely extracts and parses the `:status` pseudo-header into a workable integer representation.
- **Range detecting logic**: Uses integer division (`code / 100 == 5`) to efficiently classify all 5xx errors rather than comparing against bounds.
- **Status overriding**: Modifies the `:status` header to 404 whenever the aforementioned 5xx range test evaluates to true.

## Configuration

No configuration required. The remapping logic (5xx → 404) is hardcoded in the plugin source.

**Customization examples**:

1. **Remap to different codes**:
   ```cpp
   static int mapResponseCode(int response_code) {
       switch (response_code) {
           case 500: return 503;  // Internal Error → Service Unavailable
           case 502: return 503;  // Bad Gateway → Service Unavailable
           case 503: return 503;  // Keep Service Unavailable
           default: return response_code;
       }
   }
   ```

2. **Preserve specific 5xx codes**:
   ```cpp
   static int mapResponseCode(int response_code) {
       if (response_code == 503) {
           return 503;  // Keep 503 unchanged
       }
       return (response_code / 100 == 5) ? 404 : response_code;
   }
   ```

3. **Remap to 200 (hide all errors)**:
   ```cpp
   static int mapResponseCode(int response_code) {
       return (response_code / 100 == 5) ? 200 : response_code;
   }
   ```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/overwrite_errcode:plugin_rust.wasm

# C++
bazelisk build //samples/overwrite_errcode:plugin_cpp.wasm

# Go
bazelisk build //samples/overwrite_errcode:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/overwrite_errcode/tests.textpb \
    --plugin /mnt/bazel-bin/samples/overwrite_errcode/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/overwrite_errcode:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **With500StatusCodeChangeTo404** | Modifies a 500 error code to 404 Not Found before responding to the client. |
| **With502StatusCodeChangeTo404** | Modifies a 502 error code to 404 Not Found before responding to the client. |
| **With200StatusCodeNothingChanges** | Permits successful 200 OK responses to pass unmodified. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Security Considerations

**Important**: Remapping 5xx errors to 4xx codes can hide important operational issues:
- **Monitoring impact**: Error rates in monitoring systems may be misreported
- **Debugging difficulty**: Makes troubleshooting harder since the original error is lost
- **Client confusion**: Clients may misinterpret 404 when the actual problem is server-side

**Note**: When using this pattern, logging the original status code before remapping, using it selectively, preserving original codes in internal headers, and monitoring backend errors separately can help mitigate these issues.