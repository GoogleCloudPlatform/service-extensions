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

## Implementation Notes

- **Referer validation**: The plugin checks the `Referer` header for an allowed domain via substring matching.
- **Request ID generation**: C++ uses `absl::Uniform<uint64_t>` and Rust uses the `uuid` crate to generate a unique ID for rejected requests.
- **Blocking response**: Failed validations result in a 403 response sent directly from the plugin. C++ returns `FilterHeadersStatus::ContinueAndEndStream` and Rust returns `Action::Pause`.
- **Success marker**: Allowed requests receive a custom header indicating they passed validation.

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

| Scenario | Description |
|---|---|
| **NoForbiddenReferer** | Allows the request and adds the success marker header when the referer contains the allowed domain. |
| **WithForbiddenReferer** | Blocks the request, logs the event, and returns a 403 Forbidden response with a tracking ID when the referer is unauthorized. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [ ] Go (not available)
