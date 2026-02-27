# A/B Testing Plugin

This plugin implements A/B testing by routing a percentage of users to a v2 endpoint based on a deterministic hash of their user ID. It rewrites the request path from `/v1/` to `/v2/` for eligible users, allowing gradual rollout of new features or versions. Use this plugin when you need to split traffic between two versions of an API or service based on user identity. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_http_request_headers` callback.
2. The plugin extracts the `:path` header and checks if it starts with `/v1/`.
3. If the path contains a `user` query parameter, the plugin computes a deterministic hash of the user ID and reduces it to a value between 0 and 99.
4. If the hash value is less than or equal to the configured percentile (50), the plugin rewrites the path by replacing `/v1/` with `/v2/`, preserving the rest of the path and all query parameters.
5. The plugin returns `Action::Continue`, forwarding the (potentially modified) request to the upstream server.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Inspects the `:path` header and rewrites it from `/v1/` to `/v2/` for eligible users |

## Key Code Walkthrough

The core logic is conceptually identical across all three language implementations, though implementation details vary:

- **Path extraction and validation** — The plugin reads the `:path` pseudo-header and checks if it starts with `/v1/` (case-insensitive in C++ and Go, case-sensitive after lowercasing in Rust).

- **User extraction** — The plugin parses the query string to extract the `user` parameter:
  - **C++** uses `boost::urls::parse_relative_ref` to parse the path and `url->params().find("user")` to retrieve the value.
  - **Go** uses `url.Parse` and `u.Query().Get("user")` from the standard library.
  - **Rust** constructs a full URL (`http://example.com{path}`) and uses the `url` crate's `query_pairs()` iterator to find the `user` key.

- **Hash-based routing** — The plugin computes a deterministic hash of the user ID and checks if it falls within the percentile:
  - **C++** uses `std::hash<std::string_view>{}(user) % 100` to produce a value between 0 and 99.
  - **Go** uses FNV-1a 64-bit hashing (`fnv.New64a()`) and reduces the result modulo 100.
  - **Rust** implements a custom hash function that sums the ASCII values of the user string and adds `3 × user.len()` before taking modulo 100. This custom implementation was chosen to match the C++ test expectations for specific inputs like `"userAAA"`.

- **Path rewriting** — If the hash is ≤ 50, the plugin replaces `/v1/` with `/v2/`:
  - **`replaceRequestHeader(":path", new_path)`** (C++)
  - **`proxywasm.ReplaceHttpRequestHeader(":path", newPath)`** (Go)
  - **`self.set_http_request_header(":path", Some(&new_path))`** (Rust)

The percentile threshold is hardcoded to 50, meaning approximately 50% of users (with distinct user IDs) will be routed to v2.

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

| Scenario | Input | Output |
|---|---|---|
| **WithHashBelowThresholdRedirectsToV2File** | `:path: /v1/file.png?user=user1` | `:path: /v2/file.png?user=user1` (hash of `user1` ≤ 50, path rewritten) |
| **WithHashBelowThresholdRedirectsToV2FileIgnoringQueryParam** | `:path: /v1/file.png?user=user1&param=value` | `:path: /v2/file.png?user=user1&param=value` (hash of `user1` ≤ 50, all query params preserved) |
| **WithHashAboveThresholdKeepTheSame** | `:path: /v1/file.png?user=userAAA` | `:path: /v1/file.png?user=userAAA` (hash of `userAAA` > 50, no rewrite) |
| **WithAnotherPathKeepTheSame** | `:path: /v1alpha/file.png?user=user1` | `:path: /v1alpha/file.png?user=user1` (path does not start with `/v1/`, no rewrite) |
| **WithoutUserKeepTheSame** | `:path: /v1/file.png` | `:path: /v1/file.png` (no `user` query parameter, no rewrite) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)