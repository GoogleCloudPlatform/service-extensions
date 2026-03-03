# Remove Set-Cookie Plugin

This plugin removes all `Set-Cookie` headers from HTTP responses, effectively preventing the backend from setting cookies on clients. This is useful for implementing stateless architectures, enforcing security policies, or preventing cookie-based tracking. Use this plugin when you need to strip cookies for compliance reasons, implement cookie-free CDN caching, or enforce a no-cookies policy on specific routes. It operates during the **response headers** processing phase.

## How It Works

1. The proxy receives an HTTP response from the upstream server and invokes the plugin's `on_http_response_headers` callback.

2. The plugin calls the header removal function with the header name `"Set-Cookie"`:
   - **C++**: `removeResponseHeader("Set-Cookie")`
   - **Go**: `proxywasm.RemoveHttpResponseHeader("Set-Cookie")`
   - **Rust**: `self.set_http_response_header("Set-Cookie", None)`

3. **All instances removed**: HTTP allows multiple headers with the same name (e.g., multiple `Set-Cookie` headers for different cookies). The removal function deletes **all** instances of the specified header.

4. **Case-insensitive**: Header names are case-insensitive per HTTP specification, so `Set-Cookie`, `set-cookie`, and `SET-COOKIE` are all treated identically.

5. **Other headers preserved**: All other response headers remain unchanged.

6. The plugin returns `Continue` / `ActionContinue`, forwarding the modified response to the client.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_response_headers` | Removes all `Set-Cookie` headers from the response |

## Key Code Walkthrough

The implementation is remarkably simple across all three languages:

- **C++**:
  ```cpp
  FilterHeadersStatus onResponseHeaders(uint32_t headers, bool end_of_stream) override {
      // Remove all Set-Cookie headers from the response
      removeResponseHeader("Set-Cookie");
      return FilterHeadersStatus::Continue;
  }
  ```
  Single function call removes all instances of the header.

- **Go**:
  ```go
  func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
      // Remove all Set-Cookie headers from the response
      if err := proxywasm.RemoveHttpResponseHeader("Set-Cookie"); err != nil {
          proxywasm.LogErrorf("failed to remove Set-Cookie header: %v", err)
      }
      return types.ActionContinue
  }
  ```
  Includes error logging for debugging, though removal typically doesn't fail.

- **Rust**:
  ```rust
  fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
      // Remove all Set-Cookie headers from the response
      self.set_http_response_header("Set-Cookie", None);
      return Action::Continue;
  }
  ```
  Uses `set_http_response_header()` with `None` value to remove the header. This API is consistent with setting headers (using `Some(value)`) vs. removing them (using `None`).

### API Differences

**Header Removal APIs**:
- **C++**: `removeResponseHeader(name)` - Explicit removal function
- **Go**: `RemoveHttpResponseHeader(name)` - Explicit removal function  
- **Rust**: `set_http_response_header(name, None)` - Uses set API with `None` value

**Behavior consistency**: All implementations remove **all** instances of the specified header name, not just the first one.

## Configuration

No configuration required. The plugin always removes all `Set-Cookie` headers.

**Customization examples**:

1. **Remove different header**:
   ```cpp
   removeResponseHeader("Server");  // Hide server version
   ```

2. **Conditional removal**:
   ```cpp
   // Only remove cookies for specific paths
   auto path = getRequestHeader(":path");
   if (path && path->view().starts_with("/api/")) {
       removeResponseHeader("Set-Cookie");
   }
   ```

3. **Remove multiple headers**:
   ```cpp
   removeResponseHeader("Set-Cookie");
   removeResponseHeader("X-Custom-Header");
   removeResponseHeader("X-Debug-Info");
   ```

4. **Selective cookie removal** (more complex):
   ```cpp
   // Remove specific cookies only (requires parsing)
   auto cookies = getResponseHeaderPairs();
   for (const auto& [name, value] : cookies) {
       if (name == "Set-Cookie" && value.find("tracking") != string::npos) {
           // Remove tracking cookies only
       }
   }
   ```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/remove_setcookie:plugin_rust.wasm

# C++
bazelisk build //samples/remove_setcookie:plugin_cpp.wasm

# Go
bazelisk build //samples/remove_setcookie:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/remove_setcookie/tests.textpb \
    --plugin /mnt/bazel-bin/samples/remove_setcookie/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/remove_setcookie:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **RemovesSingleSetCookie** | `Set-Cookie: sessionid=1234` | No `Set-Cookie` header (removed) |
| **RemovesMultipleSetCookies** | `Set-Cookie: sessionid=1234`, `Set-Cookie: user=john` (two instances) | No `Set-Cookie` headers (both removed) |
| **LeavesOtherHeaders** | `Content-Type: text/html`, `Set-Cookie: sessionid=abcd` | `Content-Type: text/html` (preserved); `Set-Cookie` removed |
| **NoSetCookieInResponse** | No `Set-Cookie` header | No `Set-Cookie` header (no-op, no error) |
| **CaseInsensitiveRemoval** | `set-cookie: sessionid=5678` (lowercase) | No `set-cookie` header (case-insensitive removal works) |
| **MixedCaseRemoval** | `SeT-CoOkIe: test=value` (mixed case) | No `SeT-CoOkIe` header (case-insensitive removal works) |
| **CombinedHeaderOperations** | `Set-Cookie: to-be-removed`, `Cache-Control: max-age=3600` | `Cache-Control: max-age=3600` (preserved); `Set-Cookie` removed |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Use Cases

1. **Stateless architecture**: Enforce statelessness by preventing cookie-based sessions.

2. **Privacy/compliance**: Strip tracking cookies to comply with privacy regulations (GDPR, CCPA).

3. **CDN caching**: Remove cookies to enable efficient caching of responses (cookies prevent caching).

4. **Security policy**: Prevent cookie-based vulnerabilities (XSS, CSRF) by not using cookies.

5. **API gateway**: Enforce cookie-free APIs for better REST compliance.

6. **Testing**: Remove production cookies in staging/testing environments.

## HTTP Set-Cookie Header

The `Set-Cookie` header tells browsers to store cookies:

**Example**:
```http
Set-Cookie: sessionid=abc123; Path=/; HttpOnly; Secure
Set-Cookie: user=john; Domain=.example.com; Max-Age=3600
```

**Multiple instances**: Servers often send multiple `Set-Cookie` headers in a single response to set multiple cookies. HTTP allows this by design.

**This plugin removes all of them**.

## Security Considerations

**Best practices**:
1. Use this plugin selectively (e.g., only on API routes, not on web UI routes)
2. Ensure backend uses alternative authentication (JWT in headers, OAuth tokens)
3. Document the no-cookies policy for API consumers
4. Test thoroughly to ensure no functionality breaks

## Comparison: Cookie Removal vs. Cookie Filtering

| Approach | Implementation | Use Case |
|----------|----------------|----------|
| **Remove all** (this plugin) | Single line: `removeResponseHeader("Set-Cookie")` | Complete stateless architecture |
| **Selective filtering** | Parse and conditionally remove | Remove tracking cookies only |
| **Cookie transformation** | Parse, modify values, re-add | Sanitize cookie values |

## Example: Conditional Removal

For more complex scenarios, you might want conditional removal:

```cpp
FilterHeadersStatus onResponseHeaders(uint32_t headers, bool end_of_stream) override {
    // Only remove cookies for API paths
    auto path = getRequestHeader(":path");
    if (path && absl::StartsWith(path->view(), "/api/")) {
        removeResponseHeader("Set-Cookie");
        LOG_INFO("Removed Set-Cookie headers for API request");
    }
    return FilterHeadersStatus::Continue;
}
```

This allows cookies on web UI routes (`/web/*`) but removes them on API routes (`/api/*`).
