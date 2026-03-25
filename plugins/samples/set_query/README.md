# Set Query Plugin

This plugin demonstrates advanced URL query parameter manipulation by adding or replacing a specific query parameter in request URLs. It sets the `key` parameter to `"new val"` (URL-encoded as `"new+val"`), either adding it if it doesn't exist or replacing it if it does. The plugin also ensures the parameter appears at the end of the query string and preserves URL fragments. Use this plugin when you need to inject query parameters, normalize parameter values, or add tracking parameters to URLs. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. **URL parsing**: The plugin reads the `:path` pseudo-header and parses it as a URL:
   - **C++**: Uses Boost.URL's `parse_uri_reference()` to parse relative URLs
   - **Rust**: Uses the `url` crate with a dummy base URL (`http://example.com`)

3. **Parameter removal** (if exists): The plugin removes any existing `key` parameter from the query string:
   - **C++**: `url->params(opt).erase("key")`
   - **Rust**: Filters out `key` from `query_pairs()`

4. **URL encoding**: The value `"new val"` is URL-encoded:
   - Spaces encoded as `+` (not `%20`) using `space_as_plus` option
   - Result: `"new+val"`

5. **Parameter addition**: The plugin adds `key=new+val` to the end of the query string:
   - **C++**: `url->params(opt).set("key", val)`
   - **Rust**: `edit.query_pairs_mut().append_pair("key", "new val")`

6. **Path replacement**: The plugin updates the `:path` header with the modified URL, preserving:
   - Original path
   - All other query parameters
   - URL fragments (e.g., `#section`)

7. The plugin returns `Continue` / `Action::Continue`, forwarding the modified request.

## Implementation Notes

- **URL structuring**: Accurately processes requested path layouts including complex relative URIs or disparate query strings utilizing parsing libraries like `Boost.URL` (C++) or `url` (Rust).
- **String replacement**: Erases prior configurations for the targeting parameter ensuring no conflicting states exist.
- **URL encoding**: Securely implements HTML form style URL-encoding explicitly dictating that spaces emit as `+`.
- **Parameter serialization**: Rewrites the final `key` string value accurately at the tail end of the query without accidentally dropping URL fragments.

## Configuration

No configuration required. The parameter name (`key`) and value (`"new val"`) are hardcoded in the plugin source.

**Customization examples**:

1. **Different parameter name and value**:
   ```cpp
   // C++
   url->params(opt).erase("user_id");
   url->params(opt).set("user_id", "12345");
   ```
   ```rust
   // Rust
   let query = url.query_pairs().filter(|(k, _)| k != "user_id");
   // ...
   .append_pair("user_id", "12345");
   ```

2. **Add multiple parameters**:
   ```cpp
   // C++
   url->params(opt).set("key", val);
   url->params(opt).set("source", "proxy");
   url->params(opt).set("version", "v2");
   ```

3. **Dynamic values from headers**:
   ```cpp
   // C++
   auto user_id = getRequestHeader("X-User-ID");
   if (user_id) {
       url->params(opt).set("user_id", user_id->toString());
   }
   ```

4. **Conditional parameter addition**:
   ```cpp
   // Only add for certain paths
   if (path->view().starts_with("/api/")) {
       url->params(opt).set("key", val);
   }
   ```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/set_query:plugin_rust.wasm

# C++
bazelisk build //samples/set_query:plugin_cpp.wasm
```

**Note**: Only C++ and Rust implementations are available for this plugin (no Go version).

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/set_query/tests.textpb \
    --plugin /mnt/bazel-bin/samples/set_query/plugin_rust.wasm

# Using Bazel (both languages)
bazelisk test --test_output=all //samples/set_query:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **NoPath** | Avoids parameter injection entirely when no `:path` header is present. |
| **AddToken** | Appends the URL-encoded query parameter correctly onto standard paths. |
| **ReplaceToken** | Removes an existing key value completely before successfully overriding it at the end of the query. |
| **PreserveFragment** | Safely manages appending the new query parameter in front of any encoded URL fragments (like `#e`). |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [ ] Go (not available)

## URL Encoding Details

**Space encoding**: The plugin uses `+` for spaces instead of `%20`:
- Standard: `application/x-www-form-urlencoded` (HTML forms)
- Input: `"new val"`
- Output: `"new+val"`

**Both encodings are valid**:
- `key=new+val` (HTML form style)
- `key=new%20val` (percent-encoding style)

Servers decode both formats identically.

## URL Component Preservation

The plugin preserves all URL components:

**Example transformation**:
```
Input:  /path/to/resource?existing=param&key=old#fragment
                          ^^^^^^^^^^^^^^ ^^^^^^^^
                          preserved      replaced
Output: /path/to/resource?existing=param&key=new+val#fragment
        ^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^ ^^^^^^^^^^^ ^^^^^^^^^
        path preserved    params ordered new param   fragment preserved
```

**Component handling**:
- Path: `/path/to/resource` — Preserved
- Query parameters: `?existing=param` — Preserved and reordered
- Fragment: `#fragment` — Preserved at end
- Encoding: Special characters properly encoded

## Use Cases

1. **Tracking parameters**: Add UTM parameters or tracking codes to all requests.

2. **API versioning**: Inject version parameters for routing or analytics.

3. **Security tokens**: Add CSRF tokens or nonces to requests.

4. **A/B testing**: Add experiment identifiers for backend logic.

5. **Debug flags**: Inject debug parameters in testing environments.

6. **Cache busting**: Add timestamps or version parameters to bypass caching.

## Example Use Cases

**Tracking injection**:
```cpp
// Add Google Analytics parameters
url->params(opt).set("utm_source", "proxy");
url->params(opt).set("utm_medium", "web");
url->params(opt).set("utm_campaign", "2024");
```

**API key injection**:
```cpp
// Add API key from header to query
auto api_key = getRequestHeader("X-API-Key");
if (api_key) {
    url->params(opt).set("api_key", api_key->toString());
}
```

**Cache busting**:
```cpp
// Add timestamp to bypass caching
auto timestamp = std::to_string(std::time(nullptr));
url->params(opt).set("_", timestamp);
```

## Security Considerations

**Best practices**:
1. Validate parameter values before injection
2. Use allowlists for parameter names
3. Properly encode all values (the plugin does this)
4. Document which parameters are injected
5. Consider parameter precedence (backend should validate)