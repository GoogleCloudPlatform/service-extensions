# Redirect Plugin

This plugin demonstrates HTTP redirection by intercepting requests to specific path prefixes and sending 301 Moved Permanently responses with new locations. It redirects any requests starting with `/foo/` to `/bar/`, preserving the rest of the path. Use this plugin when you need to implement path-based redirects, migrate URL structures, or enforce canonical URLs without modifying backend services. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. **Path extraction**: The plugin reads the `:path` pseudo-header (e.g., `/foo/images/picture.png`).

3. **Prefix matching**: The plugin checks if the path starts with `/foo/`:
   - Uses `absl::StartsWith` (C++), `strings.HasPrefix` (Go), or `starts_with` (Rust)
   - Only matches paths that begin with the prefix (e.g., `/foo/page` matches, `/main/foo/page` does not)

4. **Path rewriting**: If the prefix matches:
   - The plugin constructs a new path by replacing `/foo/` with `/bar/`
   - Example: `/foo/images/picture.png` → `/bar/images/picture.png`

5. **Redirect response**: The plugin sends an immediate 301 response:
   - **Status code**: 301 (Moved Permanently)
   - **Headers**: `Location: <new_path>`
   - **Body**: `"Content moved to <new_path>"`
   - Returns `ContinueAndEndStream` / `ActionPause` to stop processing

6. **Non-matching paths**: If the prefix doesn't match, the request continues normally to the upstream server.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Checks path prefix, sends 301 redirect if matched, or allows request to continue |

## Key Code Walkthrough

The core logic is identical across all three language implementations:

- **Path prefix constants** — The old and new prefixes are defined as constants:
  - **C++**: `constexpr std::string_view old_path_prefix = "/foo/";`
  - **Go**: `const oldPathPrefix = "/foo/"`
  - **Rust**: `const OLD_PATH_PREFIX: &str = "/foo/";`

- **Path retrieval** — The plugin reads the `:path` header:
  - **C++**: `auto path = getRequestHeader(":path")->toString();`
  - **Go**: `path, err := proxywasm.GetHttpRequestHeader(":path")`
  - **Rust**: `if let Some(path) = self.get_http_request_header(":path")`

- **Prefix matching** — Each language uses its standard string function:
  - **C++**:
    ```cpp
    if (absl::StartsWith(path, old_path_prefix)) {
        std::string new_path = absl::StrCat(
            new_path_prefix, 
            path.substr(old_path_prefix.length())
        );
    ```
    Uses Abseil's `StartsWith` for efficient prefix checking and `StrCat` for string concatenation.

  - **Go**:
    ```go
    if strings.HasPrefix(path, oldPathPrefix) {
        newPath := newPathPrefix + strings.TrimPrefix(path, oldPathPrefix)
    ```
    Uses standard library `HasPrefix` and `TrimPrefix` for clean prefix replacement.

  - **Rust**:
    ```rust
    if path.starts_with(OLD_PATH_PREFIX) {
        let new_path = format!(
            "{}{}",
            NEW_PATH_PREFIX,
            &path[OLD_PATH_PREFIX.len()..]
        );
    ```
    Uses string slicing to extract the suffix after the prefix.

- **Redirect response** — All implementations send a 301 with Location header:
  - **C++**:
    ```cpp
    sendLocalResponse(
        301,                                      // Status code
        "",                                        // Details
        absl::StrCat("Content moved to ", new_path),  // Body
        {{"Location", new_path}}                  // Headers
    );
    return FilterHeadersStatus::ContinueAndEndStream;
    ```

  - **Go**:
    ```go
    headers := [][2]string{{"Location", newPath}}
    body := []byte("Content moved to " + newPath)
    proxywasm.SendHttpResponse(301, headers, body, -1)
    return types.ActionPause
    ```

  - **Rust**:
    ```rust
    self.send_http_response(
        301,
        vec![("Location", new_path.as_str())],
        Some(format!("Content moved to {}", new_path).as_bytes()),
    );
    return Action::Pause;
    ```

- **HTTP 301 vs 302**: The plugin uses 301 (Moved Permanently) which:
  - Tells clients and search engines the resource has permanently moved
  - Browsers cache the redirect
  - SEO authority transfers to the new URL
  - Use 302 (Found) for temporary redirects or 307/308 for method-preserving redirects

## Configuration

No configuration required. The old and new path prefixes are hardcoded in the plugin source.

**Customization examples**:

1. **Different path prefixes**:
   ```cpp
   constexpr std::string_view old_path_prefix = "/api/v1/";
   constexpr std::string_view new_path_prefix = "/api/v2/";
   ```

2. **Multiple redirects** (requires code modification):
   ```cpp
   struct Redirect {
       std::string_view old_prefix;
       std::string_view new_prefix;
   };
   
   const std::vector<Redirect> redirects = {
       {"/foo/", "/bar/"},
       {"/old/", "/new/"},
       {"/api/v1/", "/api/v2/"}
   };
   ```

3. **Domain redirect** (add domain to Location):
   ```cpp
   std::string new_location = "https://new-domain.com" + new_path;
   sendLocalResponse(301, "", ..., {{"Location", new_location}});
   ```

4. **Use 302 for temporary redirect**:
   ```cpp
   sendLocalResponse(302, "", ..., {{"Location", new_path}});
   ```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/redirect:plugin_rust.wasm

# C++
bazelisk build //samples/redirect:plugin_cpp.wasm

# Go
bazelisk build //samples/redirect:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/redirect/tests.textpb \
    --plugin /mnt/bazel-bin/samples/redirect/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/redirect:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **NoRedirect** | `:path: /main/somepage/otherpage` (prefix not matched) | Request continues with original path; no `Location` header |
| **DoRedirect** | `:path: /foo/images/picture.png` (prefix matched) | 301 redirect with `Location: /bar/images/picture.png`; body: `"Content moved to /bar/images/picture.png"` |
| **DoRedirect** (duplicate name in test) | `:path: /main/foo/images/picture.png` (prefix not at beginning) | Request continues with original path; no `Location` header (only matches prefix at start) |

**Note**: The third test has a duplicate name "DoRedirect" which should be renamed (e.g., "NoRedirectWhenPrefixNotAtStart").

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Use Cases

1. **URL migration**: Redirect old URL structures to new ones during site migrations.

2. **API versioning**: Redirect `/api/v1/` to `/api/v2/` while maintaining backward compatibility.

3. **Canonical URLs**: Enforce canonical URL structures for SEO (e.g., redirect `/products` to `/shop/products`).

4. **Directory reorganization**: Redirect moved content without modifying backend services.

5. **A/B testing**: Redirect specific paths to experimental versions.

## HTTP Redirect Status Codes

| Code | Name | Meaning | Caching | Method Preserved |
|------|------|---------|---------|------------------|
| 301 | Moved Permanently | Resource permanently moved | Yes | No (may change to GET) |
| 302 | Found | Temporary redirect (legacy) | No | No (may change to GET) |
| 303 | See Other | Redirect after POST | No | No (changes to GET) |
| 307 | Temporary Redirect | Temporary redirect | No | Yes |
| 308 | Permanent Redirect | Permanent redirect | Yes | Yes |

**Plugin uses 301**: Appropriate for permanent URL changes where SEO authority should transfer.

## Example Redirect Patterns

**Path prefix replacement**:
```
/foo/images/pic.png → /bar/images/pic.png
/foo/page           → /bar/page
/foo/               → /bar/
```

**Domain migration**:
```
http://old.com/foo/page → https://new.com/bar/page
```

**API versioning**:
```
/api/v1/users → /api/v2/users
```

**Subdirectory to subdomain**:
```
/blog/post-1 → https://blog.example.com/post-1
```
