# Config Denylist Plugin

This plugin implements token-based access control using a configurable denylist. It reads a list of blocked tokens from a configuration file at startup and rejects requests that contain any of those tokens in the `User-Token` header with a 403 Forbidden response. Use this plugin when you need to block specific API keys, user tokens, or identifiers, implement basic authentication filtering, or maintain a dynamic blocklist without redeploying your application. It operates during the **request headers** processing phase.

## How It Works

1. **Plugin initialization**: When the plugin starts, the proxy invokes `on_configure` (root context):
   - The plugin reads the configuration file containing a denylist of tokens (one token per line, whitespace-separated).
   - The plugin parses the configuration and stores the tokens in a hash set for O(1) lookup performance.
   - The plugin logs the number of tokens loaded (e.g., `"Config keys size 3"`).

2. **Request processing**: When the proxy receives an HTTP request, it invokes `on_http_request_headers`:
   - The plugin reads the `User-Token` header from the request.
   - If the header is missing, the plugin sends a 403 Forbidden response with body `"Access forbidden - token missing.\n"` and stops processing.
   - If the header value is in the denylist, the plugin sends a 403 Forbidden response with body `"Access forbidden.\n"` and stops processing.
   - If the header value is not in the denylist, the plugin allows the request to proceed to the upstream server.

3. **No-config fallback**: If no configuration file is provided, the plugin loads an empty denylist (size 0) and allows all tokens.

## Implementation Notes

- **Configuration parsing**: Parses a given text block at initialization and splits it by whitespace to build a denylist set.
- **Optimization via shared references**: Rust utilizes an `Rc<HashSet<String>>` to shallow copy the configuration into HTTP contexts efficiently, and C++ shares `string_view` references from the root context.
- **Token validation**: Reads the `User-Token` header and verifies its absence in the denylist; missing headers or matches result in an immediate 403 Forbidden response.

## Configuration

The plugin expects a plain text configuration file with one denied token per line. Tokens can be separated by any whitespace (spaces, tabs, newlines).

**Example configuration** (`tests.config`):
```
no-user
bad-user
evil-user
```

This configuration denies requests with `User-Token: no-user`, `User-Token: bad-user`, or `User-Token: evil-user`.

**No-config behavior**: If no configuration is provided, the plugin loads an empty denylist and allows all tokens.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/config_denylist:plugin_rust.wasm

# C++
bazelisk build //samples/config_denylist:plugin_cpp.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended) - with config
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/config_denylist/tests.textpb \
    --plugin /mnt/bazel-bin/samples/config_denylist/plugin_rust.wasm \
    --config /mnt/samples/config_denylist/tests.config

# Using Docker (recommended) - without config
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/config_denylist/tests_noconfig.textpb \
    --plugin /mnt/bazel-bin/samples/config_denylist/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/config_denylist:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb) (with config file):

| Scenario | Description |
|---|---|
| **LoadsConfig** | Successfully parses tokens from the configuration file at startup. |
| **AllowsGoodToken** | Permits requests that provide a valid token not found in the denylist. |
| **DeniesBadToken** | Rejects requests providing a token present in the denylist. |
| **DeniesMissingToken** | Rejects requests entirely lacking the required token header. |
| **LoadsNoConfig** | Successfully initializes with an empty denylist when no configuration file is present. |
| **AllowsBadToken** | Allows historically bad tokens through when no configuration denylist is loaded. |

Derived from [`tests_noconfig.textpb`](tests_noconfig.textpb) (without config file):

| Scenario | Description |
|---|---|
| **LoadsConfig** | Successfully parses tokens from the configuration file at startup. |
| **AllowsGoodToken** | Permits requests that provide a valid token not found in the denylist. |
| **DeniesBadToken** | Rejects requests providing a token present in the denylist. |
| **DeniesMissingToken** | Rejects requests entirely lacking the required token header. |
| **LoadsNoConfig** | Successfully initializes with an empty denylist when no configuration file is present. |
| **AllowsBadToken** | Allows historically bad tokens through when no configuration denylist is loaded. |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [ ] Go (not available)
