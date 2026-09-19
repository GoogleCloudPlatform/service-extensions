# CDN Token Generator

This plugin implements URL signing by intercepting response bodies (e.g., HLS/DASH manifests) and replacing matching HTTP/HTTPS URLs with signed URLs containing HMAC-SHA256 tokens. Use this plugin when you need to authenticate clients requesting video segments or static assets through Google Cloud Media CDN or similar CDNs that enforce Edge-Cache-Token validation. It operates during the **response body** processing phase with configuration loading during **plugin initialization**.

## How It Works

### Plugin Initialization

1. The proxy loads the plugin and invokes `on_configure` (C++/Rust) or `OnPluginStart` (Go).
2. The plugin reads the text-based configuration containing the CDN private key, key name, and expiration window.
3. The plugin decodes the hex-encoded private key once to save CPU cycles and stores it securely in the root context.

### Request Processing

1. The proxy intercepts the response from the upstream server and buffers it.
2. The plugin skips processing if the body exceeds the 1MB safety limit.
3. If the payload is within limits, it parses the body looking for matching URLs.
4. For every matched URL, it independently generates an HMAC-SHA256 signature using the expiration time and the decoded hex key.
5. It safely injects the signed URLs into the body string format, replacing the original URLs completely via string offset matching.
6. The modified payload is sent securely back to the client.

## Implementation Notes

- **Buffering:** All implementations buffer the HTTP response body until the end of the stream is reached to process the full payload efficiently.
- **Resource Constraints:** Processing is automatically skipped for documents over 1MB string size to mitigate potential Out-of-Memory (OOM) vulnerabilities.
- **Clock Retrieval:** Standard time retrieval logic operates natively to calculate token expiration dynamically.

## Implementation Details by Language

### Configuration Parsing
All implementations avoid heavy protobuf dependencies to parse the simple 3-field text format efficiently:

- **C++**: Uses `google::protobuf::TextFormat` since C++ plugins already depend on the core Envoy framework libraries, which include protobuf handling natively.
- **Go**: Uses `strings.Split` and a lightweight switch case, splitting lines by `\n` to manually extract properties to keep the TinyGo compilation minimal. 
- **Rust**: Uses `config_str.lines()` and pure string manipulation (`splitn(2, ':')`), decoding the initial key aggressively via the `hex` crate at boot time.

### HMAC and Cryptography
- **C++**: Leverages `BoringSSL` through `@boringssl//:crypto` (HMAC/EVP_sha256).
- **Go**: Relies natively on standard `crypto/hmac` and `crypto/sha256`.
- **Rust**: Uses the `hmac`, `sha2`, `base64`, and `hex` individual crates via standard Cargo configurations to guarantee WASM sandbox compatibility.

## Configuration

The plugin requires a configuration file with the Token parameters in plain text format.

**Example configuration** (`tests_config.textpb`):
```textpb
private_key_hex: "d8ef411f9f735c3d2b263606678ba5b7b1abc1973f1285f856935cc163e9d094"
key_name: "test-key"
expiry_seconds: 3600
```

**Format rules**:
- `private_key_hex`: Must be between 32 and 256 characters long.
- `key_name`: Required identifier mapped to your Google Cloud configuration.
- `expiry_seconds`: Limits between 60 and 86400 (24 hours).

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/cdn_token_generator:plugin_cpp.wasm

# Rust
bazelisk build //samples/cdn_token_generator:plugin_rust.wasm

# Go
bazelisk build //samples/cdn_token_generator:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/cdn_token_generator/tests.textpb \
    --plugin /mnt/bazel-bin/samples/cdn_token_generator/plugin_rust.wasm \
    --config /mnt/samples/cdn_token_generator/tests_config.textpb

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/cdn_token_generator:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb) with edge cache configurations:

| Scenario | Description |
|---|---|
| **Multiple URLs Replacement** | Can accurately find and sign multiple media URLs embedded within complex HLS/DASH payloads without breaking formats. |
| **Existing Query Params** | Cleanly appends the `Edge-Cache-Token` argument differentiating between `?` and `&` parameter joining rules. |
| **JSON Safe Injection** | Works smoothly replacing URLs nested within deep JSON API payloads accurately. |

## Available Languages

- [x] [C++](plugin.cc)
- [x] [Rust](plugin.rs)
- [x] [Go](plugin.go)
