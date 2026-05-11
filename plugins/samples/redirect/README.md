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

## Implementation Notes

- **Prefix matching**: Uses native string prefix functions (`absl::StartsWith` in C++, `strings.HasPrefix` in Go, `starts_with` in Rust) to identify matching paths.
- **Path rewriting**: Constructs the new destination URL path by splicing the new prefix with the leftover suffix from the original path.
- **Immediate response**: Triggers an HTTP 301 response immediately, bypassing the upstream destination by returning `ContinueAndEndStream` / `ActionPause`.

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

| Scenario | Description |
|---|---|
| **NoRedirect** | Allows the request to continue unchanged since the target prefix isn't matched. |
| **DoRedirect** | Matches the configured prefix and halts the request with a 301 redirect to the derived new path. |
| **DoRedirect** (duplicate name in test) | Allows the request to continue unchanged since the prefix only exists mid-path, not at the start. |

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
