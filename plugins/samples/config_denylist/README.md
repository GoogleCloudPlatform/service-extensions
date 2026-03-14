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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_configure` | Reads the configuration file, parses the denylist tokens, and stores them in a hash set |
| `on_http_request_headers` | Checks the `User-Token` header against the denylist and blocks matching tokens with a 403 response |
| `on_http_response_headers` | No-op (returns `Continue`); included for completeness |

## Key Code Walkthrough

The core logic is conceptually identical between the C++ and Rust implementations:

- **Configuration parsing** — The plugin reads and parses the denylist at startup:
  - **C++** uses `getBufferBytes(WasmBufferType::PluginConfiguration, 0, config_len)` to read the config as a single buffer, stores it in `config_` to maintain ownership, and parses it as a string view using `find_first_of(" \f\n\r\t\v", idx)` to split on whitespace. Each token is stored as a `string_view` in `tokens_` (`unordered_set<string_view>`), avoiding string copies.
  - **Rust** uses `self.get_plugin_configuration()` to read the config as bytes, converts it to a UTF-8 string, and splits it using `config_lines.lines()` followed by `.trim()` to remove whitespace. Each non-empty token is stored as a `String` in `tokens` (`Rc<HashSet<String>>`). The `Rc` (reference-counted pointer) allows shallow copying the hash set to HTTP contexts without duplicating the data.

  Both implementations log the number of tokens loaded using `LOG_INFO` (C++) or `info!` (Rust).

- **Token validation** — The plugin checks the `User-Token` header against the denylist:
  - **C++** uses `getRequestHeader("User-Token")` to retrieve the header. If missing or empty, it sends a 403 with `"Access forbidden - token missing.\n"`. If present, it checks `tokens_.count(token->view()) > 0` to determine if the token is in the denylist.
  - **Rust** uses `self.get_http_request_header("User-Token")` with pattern matching. If `None`, it sends a 403 with `"Access forbidden - token missing.\n"`. If `Some(auth_header)`, it checks `self.tokens.contains(&auth_header)` to determine if the token is in the denylist.

- **Blocking response** — When a token is denied, the plugin sends a 403 Forbidden response:
  - **C++** uses `sendLocalResponse(403, "", "Access forbidden.\n", {})` and returns `FilterHeadersStatus::StopAllIterationAndWatermark` to stop processing.
  - **Rust** uses `self.send_http_response(403, vec![], Some(b"Access forbidden.\n"))` and returns `Action::Pause` to stop processing.

- **Performance optimization** — Both implementations use efficient data structures to avoid copying:
  - **C++** stores the config buffer in the root context (`config_`) and uses `string_view` references to avoid string copies. The HTTP context holds a reference to the root context's token set.
  - **Rust** uses `Rc<HashSet<String>>` to share the token set between the root context and HTTP contexts. Cloning an `Rc` is a shallow copy (only increments a reference count), avoiding expensive deep copies of the hash set on every request.

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

| Scenario | Input | Output |
|---|---|---|
| **LoadsConfig** | Plugin initialization with `tests.config` | Log message `Config keys size 3` (3 tokens loaded: `no-user`, `bad-user`, `evil-user`) |
| **AllowsGoodToken** | Request with `User-Token: good-user` | Request passes through with `User-Token: good-user` header (token not in denylist) |
| **DeniesBadToken** | Request with `User-Token: bad-user` | 403 Forbidden response with body `"Access forbidden.\n"` (token is in denylist) |
| **DeniesMissingToken** | Request with no `User-Token` header | 403 Forbidden response with body `"Access forbidden - token missing.\n"` (header required) |

Derived from [`tests_noconfig.textpb`](tests_noconfig.textpb) (without config file):

| Scenario | Input | Output |
|---|---|---|
| **LoadsNoConfig** | Plugin initialization without config | Log message `Config keys size 0` (empty denylist) |
| **AllowsBadToken** | Request with `User-Token: bad-user` | Request passes through with `User-Token: bad-user` header (empty denylist allows all tokens) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [ ] Go (not available)
