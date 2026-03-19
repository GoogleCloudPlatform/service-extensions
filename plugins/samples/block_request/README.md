# Block Request Plugin

This plugin implements referer-based access control by validating that incoming requests originate from an allowed domain. It checks the `Referer` header against an allowed domain (`safe-site.com`) and blocks requests from unauthorized origins with a 403 Forbidden response. Use this plugin when you need to prevent hotlinking, implement basic origin validation, or restrict access to trusted referrers. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.
2. The plugin reads the `Referer` header and checks if it contains the allowed domain (`safe-site.com`).
3. If the `Referer` header is missing or does not contain the allowed domain:
   - The plugin generates a unique request ID (using a random number generator in C++ or UUID in Rust).
   - The plugin sends a 403 Forbidden response with a body containing the request ID (e.g., `Forbidden - Request ID: 1234567890`).
   - The plugin logs the blocked request with the request ID for auditing.
   - The plugin returns `Action::Pause` (Rust) or `FilterHeadersStatus::ContinueAndEndStream` (C++), stopping further processing.
4. If the `Referer` header contains the allowed domain:
   - The plugin adds a `my-plugin-allowed: true` header to the request to indicate the request passed validation.
   - The plugin returns `Action::Continue`, forwarding the request to the upstream server.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Validates the `Referer` header and blocks unauthorized requests with a 403 response |

## Key Code Walkthrough

The core logic is conceptually identical between the C++ and Rust implementations:

- **Referer validation** — The plugin reads the `Referer` header and checks if it contains the allowed domain:
  - **C++** uses `getRequestHeader("Referer")` and `absl::StrContains(referer->view(), kAllowedReferer)` to perform a substring match. If the header is missing (`!referer`) or doesn't contain the allowed domain, the request is blocked.
  - **Rust** uses `self.get_http_request_header("Referer")` and `.map_or(true, |r| !r.contains(ALLOWED_REFERER))` to check if the header is missing or doesn't contain the allowed domain.

  The allowed domain is hardcoded as a constant: `kAllowedReferer = "safe-site.com"` (C++) / `ALLOWED_REFERER = "safe-site.com"` (Rust).

- **Request ID generation** — Each blocked request is assigned a unique ID for tracking:
  - **C++** uses `absl::Uniform<uint64_t>(bitgen_)` from a `MyRootContext` to generate a random 64-bit unsigned integer. The `bitgen_` is an `absl::BitGen` instance stored in the root context.
  - **Rust** uses `Uuid::new_v4().simple()` from the `uuid` crate to generate a UUID in simple format (32 hex digits without hyphens).

- **Blocking response** — When validation fails, the plugin sends a 403 Forbidden response:
  - **C++** uses `sendLocalResponse(403, "", "Forbidden - Request ID: " + requestId, {})` to send the response with the request ID in the body.
  - **Rust** uses `self.send_http_response(403, vec![], Some(format!("Forbidden - Request ID: {}", request_id).as_bytes()))`.

  Both implementations also log the blocked request with the request ID using `LOG_INFO` (C++) or `info!` (Rust).

- **Success marker** — For allowed requests, the plugin adds a header to indicate successful validation:
  - **`addRequestHeader("my-plugin-allowed", "true")`** (C++)
  - **`self.add_http_request_header("my-plugin-allowed", "true")`** (Rust)

  This header can be used by upstream services or other plugins to confirm that the request passed referer validation.

- **Return value** — The plugin returns different values depending on the outcome:
  - Blocked requests: `FilterHeadersStatus::ContinueAndEndStream` (C++) / `Action::Pause` (Rust) to stop further processing.
  - Allowed requests: `FilterHeadersStatus::Continue` (C++) / `Action::Continue` (Rust) to proceed normally.

**Note:** Only C++ and Rust implementations are available for this plugin. There is no Go implementation in the provided source files.

## Configuration

No configuration required. The allowed referer domain is hardcoded as a constant:
- **C++**: `kAllowedReferer = "safe-site.com"`
- **Rust**: `ALLOWED_REFERER = "safe-site.com"`

To use a different domain, modify the constant and rebuild the plugin.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/block_request:plugin_rust.wasm

# C++
bazelisk build //samples/block_request:plugin_cpp.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/block_request/tests.textpb \
    --plugin /mnt/bazel-bin/samples/block_request/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/block_request:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **NoForbiddenReferer** | `Referer: https://www.safe-site.com/somepage` | `my-plugin-allowed: true` header added (request allowed, referer contains allowed domain) |
| **WithForbiddenReferer** | `Referer: https://www.forbidden-site.com/somepage` | 403 Forbidden response with body matching `Forbidden - Request ID: [hex digits]+`, log entry with request ID, no `my-plugin-allowed` header (request blocked, referer does not contain allowed domain) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [ ] Go (not available)
