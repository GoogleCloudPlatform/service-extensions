# Overwrite Header Plugin

This plugin demonstrates conditional header replacement with different behaviors for request and response headers. For request headers, it only replaces existing headers (conditional overwrite). For response headers, it always sets the header value, creating it if it doesn't exist (unconditional upsert). Use this plugin when you need to standardize header values, enforce header policies, or learn the differences between header manipulation APIs. It operates during the **request headers** and **response headers** processing phases.

## How It Works

### Request Headers (Conditional Replacement)

1. The proxy receives an HTTP request and invokes `on_http_request_headers`.

2. The plugin checks if the `RequestHeader` header exists by reading its value.

3. **If the header exists**: The plugin replaces its value with `"changed"`.

4. **If the header doesn't exist**: The plugin does nothing (header is not added).

This pattern is useful when you want to normalize existing headers without adding new ones.

### Response Headers (Unconditional Upsert)

1. The proxy receives an HTTP response from the upstream server and invokes `on_http_response_headers`.

2. The plugin unconditionally calls `replaceResponseHeader()` / `ReplaceHttpResponseHeader()` / `set_http_response_header()` with `ResponseHeader: changed`.

3. **If the header exists**: Its value is replaced with `"changed"`.

4. **If the header doesn't exist**: The header is created with value `"changed"`.

This pattern is useful when you want to ensure a header is always present with a specific value.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Conditionally replaces `RequestHeader` only if it already exists |
| `on_http_response_headers` | Unconditionally sets `ResponseHeader` (creates or replaces) |

## Key Code Walkthrough

The plugin demonstrates different header manipulation patterns:

### Request Headers (Conditional)

- **C++**:
  ```cpp
  const auto header_key = "RequestHeader";
  const auto header = getRequestHeader(header_key);
  // It will only replace the header if it already exists.
  if (header->size() > 0) {
      replaceRequestHeader(header_key, "changed");
  }
  ```
  Checks if the header exists and has content before replacing.

- **Go**:
  ```go
  headerKey := "RequestHeader"
  header, err := proxywasm.GetHttpRequestHeader(headerKey)
  if err != nil && err != types.ErrorStatusNotFound {
      panic(err)
  }
  if len(header) > 0 {
      err := proxywasm.ReplaceHttpRequestHeader(headerKey, "changed")
      if err != nil {
          panic(err)
      }
  }
  ```
  Explicitly checks for `ErrorStatusNotFound` to distinguish "header doesn't exist" from other errors.

- **Rust**:
  ```rust
  let header_key = "RequestHeader";
  if let Some(_header) = self.get_http_request_header(header_key) {
      self.set_http_request_header(header_key, Some("changed"));
  }
  ```
  Uses pattern matching (`if let Some`) to conditionally replace only if the header exists.

### Response Headers (Unconditional)

- **C++**:
  ```cpp
  // Unlike the previous example, the header will be added if it doesn't exist
  // or updated if it already does.
  replaceResponseHeader("ResponseHeader", "changed");
  ```
  No existence check — always sets the header.

- **Go**:
  ```go
  err := proxywasm.ReplaceHttpResponseHeader("ResponseHeader", "changed")
  if err != nil {
      panic(err)
  }
  ```
  Direct replacement without checking if the header exists.

- **Rust**:
  ```rust
  self.set_http_response_header("ResponseHeader", Some("changed"));
  ```
  Always sets the header (upsert behavior).

### API Behavior Differences

**`replaceHeader` / `ReplaceHttpHeader` / `set_http_header`**:
- **Behavior**: Creates the header if it doesn't exist, replaces if it does (upsert)
- **Use case**: Ensuring a header always has a specific value

**`addHeader` / `AddHttpHeader` / `add_http_header`**:
- **Behavior**: Appends to existing headers (can create multiple values)
- **Use case**: Adding additional values to multi-valued headers (e.g., `Set-Cookie`)

**Conditional replacement pattern**:
- **Behavior**: Only modifies existing headers
- **Use case**: Normalizing headers without adding new ones

## Configuration

No configuration required. Header names (`RequestHeader`, `ResponseHeader`) and values (`"changed"`) are hardcoded in the plugin source.

**Customization**:
```cpp
// C++
const auto header_key = "X-Custom-Header";
replaceRequestHeader(header_key, "new-value");
```

```rust
// Rust
const REQUEST_HEADER_KEY: &str = "X-Custom-Header";
const REQUEST_HEADER_VALUE: &str = "new-value";
```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/overwrite_header:plugin_rust.wasm

# C++
bazelisk build //samples/overwrite_header:plugin_cpp.wasm

# Go
bazelisk build //samples/overwrite_header:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/overwrite_header/tests.textpb \
    --plugin /mnt/bazel-bin/samples/overwrite_header/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/overwrite_header:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **DoNotAddRequestHeader** | Request with `OtherHeader: OtherValue` (no `RequestHeader`) | `OtherHeader: OtherValue` (unchanged); `RequestHeader` not added (conditional replacement skipped) |
| **DoAddResponseHeader** | Response with `OtherHeader: OtherValue` (no `ResponseHeader`) | `OtherHeader: OtherValue` (unchanged); `ResponseHeader: changed` added (unconditional upsert) |
| **OverwriteRequestHeader** | Request with `RequestHeader: SomeHeaderValue`, `OtherHeader: OtherValue` | `RequestHeader: changed` (value replaced); `OtherHeader: OtherValue` (unchanged) |
| **OverwriteResponseHeader** | Response with `ResponseHeader: SomeHeaderValue`, `OtherHeader: OtherValue` | `ResponseHeader: changed` (value replaced); `OtherHeader: OtherValue` (unchanged) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Use Cases

**Request headers (conditional)**:
- Normalize authentication tokens only if present
- Sanitize user-provided headers without adding defaults
- Enforce format requirements on existing headers

**Response headers (unconditional)**:
- Ensure security headers are always present (e.g., `X-Frame-Options`, `X-Content-Type-Options`)
- Override upstream header values with policy-enforced values
- Add or update cache-control headers

**Example: Security headers**:
```cpp
FilterHeadersStatus onResponseHeaders(...) override {
    // Always enforce security headers
    replaceResponseHeader("X-Frame-Options", "DENY");
    replaceResponseHeader("X-Content-Type-Options", "nosniff");
    replaceResponseHeader("Strict-Transport-Security", "max-age=31536000");
    return FilterHeadersStatus::Continue;
}
```
