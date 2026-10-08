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

## Implementation Notes

- **Header removal block**: Eradicates HTTP headers by strictly passing the header key to the `removeResponseHeader` API or equivalent null-setter (`set_http_response_header("Set-Cookie", None)` in Rust).
- **Multiple instance stripping**: Demonstrates that calling the native deletion function eliminates all instances of the case-insensitive header string simultaneously.

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

| Scenario | Description |
|---|---|
| **RemovesSingleSetCookie** | Erases a single instance of the `Set-Cookie` header. |
| **RemovesMultipleSetCookies** | Erases multiple duplicate instances of the `Set-Cookie` header simultaneously. |
| **LeavesOtherHeaders** | Confirms that entirely unrelated headers remain untouched during cookie deletion. |
| **NoSetCookieInResponse** | Operates safely as a no-op when no cookies exist to be deleted. |
| **CaseInsensitiveRemoval** | Confirms that standard lowercase headers are successfully erased. |
| **MixedCaseRemoval** | Confirms that chaotically cased headers are successfully erased. |
| **CombinedHeaderOperations** | Removes the specified header safely amidst other varied response headers. |

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
