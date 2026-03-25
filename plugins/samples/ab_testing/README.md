# A/B Testing Plugin

This plugin implements A/B testing by routing a percentage of users to a v2 endpoint based on a deterministic hash of their user ID. It rewrites the request path from `/v1/` to `/v2/` for eligible users, allowing gradual rollout of new features or versions. Use this plugin when you need to split traffic between two versions of an API or service based on user identity. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_http_request_headers` callback.
2. The plugin extracts the `:path` header and checks if it starts with `/v1/`.
3. If the path contains a `user` query parameter, the plugin computes a deterministic hash of the user ID and reduces it to a value between 0 and 99.
4. If the hash value is less than or equal to the configured percentile (50), the plugin rewrites the path by replacing `/v1/` with `/v2/`, preserving the rest of the path and all query parameters.
5. The plugin returns `Action::Continue`, forwarding the (potentially modified) request to the upstream server.

## Implementation Notes

- **Path extraction**: The plugin reads the `:path` header and handles query parameters.
- **Specific libraries used for URLs**: C++ uses `boost::urls`, Go relies on the standard `net/url`, and Rust builds a full URL and uses the `url` crate.
- **Hashing**: Device type detection / user identity routing depends on a deterministic hash of the extracted user ID. Rust implements a custom hash function to match C++ test expectations.
- **Threshold**: The 50% threshold for routing to the v2 endpoint is hardcoded as a constant.

## Configuration

No configuration required. The percentile threshold and path prefixes are hardcoded as constants:
- `a_path` / `A_PATH`: `/v1/`
- `b_path` / `B_PATH`: `/v2/`
- `percentile` / `PERCENTILE`: `50`

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/ab_testing:plugin_rust.wasm

# C++
bazelisk build //samples/ab_testing:plugin_cpp.wasm

# Go
bazelisk build //samples/ab_testing:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/ab_testing/tests.textpb \
    --plugin /mnt/bazel-bin/samples/ab_testing/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/ab_testing:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **WithHashBelowThresholdRedirectsToV2File** | Redirects to the v2 path when the user's hash is below the configured threshold. |
| **WithHashBelowThresholdRedirectsToV2FileIgnoringQueryParam** | Preserves additional query parameters while rewriting the path for users below the threshold. |
| **WithHashAboveThresholdKeepTheSame** | Makes no changes when the user's hash is above the configured threshold. |
| **WithAnotherPathKeepTheSame** | Makes no changes when the request path does not match the configured v1 path. |
| **WithoutUserKeepTheSame** | Makes no changes because the required user query parameter is missing. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)