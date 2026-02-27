# Log Calls Plugin

This plugin demonstrates the complete lifecycle of Proxy-WASM contexts by logging every callback invocation. It tracks both the root context lifecycle (plugin initialization and shutdown) and HTTP context lifecycle (per-request processing), making it an invaluable tool for understanding plugin execution flow, debugging callback ordering, and learning the Proxy-WASM programming model. Use this plugin when you need to understand callback execution order, debug lifecycle issues, or learn how Proxy-WASM contexts are created and destroyed. It operates across **all plugin lifecycle phases**.

## How It Works

The plugin logs messages at every stage of its lifecycle:

### Root Context Lifecycle (Plugin-level)

1. **`onCreate`** (Rust only): Logged when the root context object is created.
2. **`onStart` / `on_vm_start`**: Logged when the WASM VM starts and the plugin is loaded.
3. **`onConfigure` / `on_configure`**: Logged when the plugin configuration is loaded.
4. **`onDone` / `on_done`**: Logged when the root context is about to be destroyed.
5. **`onDelete` / `Drop`**: Logged when the root context is destroyed.

### HTTP Context Lifecycle (Per-request)

1. **`onCreate` / `create_http_context`**: Logged when a new HTTP context is created for an incoming request.
2. **`onRequestHeaders` / `on_http_request_headers`**: Logged when request headers are received.
3. **`onResponseHeaders` / `on_http_response_headers`**: Logged when response headers are received.
4. **`onDone` / `on_done`**: Logged when the HTTP context is about to be destroyed.
5. **`onDelete` / `Drop`**: Logged when the HTTP context is destroyed.

All callbacks return `Continue` or `true` to allow normal request processing.

## Proxy-Wasm Callbacks Used

### Root Context Callbacks

| Callback | C++ | Rust | When Called |
|----------|-----|------|-------------|
| `onCreate` | ✅ | ✅ | When root context is created |
| `onStart` / `on_vm_start` | ✅ | ✅ | When WASM VM starts |
| `onConfigure` / `on_configure` | ✅ | ✅ | When configuration is loaded |
| `onDone` / `on_done` | ✅ | ✅ | Before root context is destroyed |
| `onDelete` / `Drop` | ✅ | ✅ | When root context is destroyed |

### HTTP Context Callbacks

| Callback | C++ | Rust | When Called |
|----------|-----|------|-------------|
| `onCreate` / `create_http_context` | ✅ | ✅ | When HTTP context is created |
| `onRequestHeaders` / `on_http_request_headers` | ✅ | ✅ | When request headers are received |
| `onResponseHeaders` / `on_http_response_headers` | ✅ | ✅ | When response headers are received |
| `onDone` / `on_done` | ✅ | ✅ | Before HTTP context is destroyed |
| `onDelete` / `Drop` | ✅ | ✅ | When HTTP context is destroyed |

## Key Code Walkthrough

The plugin implementations differ slightly in how they handle object lifecycle:

- **C++ logging** — Uses `LOG_INFO` macro for all log messages:
  ```cpp
  void onCreate() override { LOG_INFO("root onCreate called"); }
  bool onStart(size_t) override {
      LOG_INFO("root onStart called");
      return true;
  }
  ```

- **Rust logging** — Uses the `log` crate's `info!` macro:
  ```rust
  fn on_vm_start(&mut self, _: usize) -> bool {
      info!("root onStart called");
      return true;
  }
  ```
  
  Rust also uses the `Drop` trait for cleanup logging:
  ```rust
  impl Drop for MyRootContext {
      fn drop(&mut self) {
          info!("root onDelete called");
      }
  }
  ```

- **Context creation in Rust** — The root context is created in the `set_root_context` closure:
  ```rust
  proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
      info!("root onCreate called");
      Box::new(MyRootContext)
  });
  ```
  
  HTTP contexts are created in `create_http_context`:
  ```rust
  fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
      info!("http onCreate called");
      Some(Box::new(MyHttpContext))
  }
  ```

## Configuration

No configuration required.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/log_calls:plugin_rust.wasm

# C++
bazelisk build //samples/log_calls:plugin_cpp.wasm
```

**Note**: Only Rust and C++ implementations are available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/log_calls/tests.textpb \
    --plugin /mnt/bazel-bin/samples/log_calls/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/log_calls:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

### Plugin Initialization Logs

| Phase | Log Message |
|-------|-------------|
| Root context creation | `root onCreate called` |
| VM start | `root onStart called` |
| Configuration load | `root onConfigure called` |

### Per-Request Logs

| Phase | Log Message |
|-------|-------------|
| HTTP context creation | `http onCreate called` |
| Request headers received | `http onRequestHeaders called` |
| Response headers received | `http onResponseHeaders called` |
| HTTP context cleanup | `http onDone called` |
| HTTP context destruction | `http onDelete called` |

### Typical Request Flow

For a single request, you will see logs in this order:

1. `root onCreate called` (plugin initialization, once)
2. `root onStart called` (plugin initialization, once)
3. `root onConfigure called` (plugin initialization, once)
4. `http onCreate called` (per request)
5. `http onRequestHeaders called` (per request)
6. `http onResponseHeaders called` (per request)
7. `http onDone called` (per request)
8. `http onDelete called` (per request)

When the plugin is unloaded:
9. `root onDone called` (plugin shutdown, once)
10. `root onDelete called` (plugin shutdown, once)

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [ ] Go (not available)

## Learning Objectives

This plugin demonstrates:

1. **Complete lifecycle visibility**: Every callback invocation is logged, showing the complete execution flow from plugin load to unload.

2. **Context creation and destruction**: Understanding when contexts are created (plugin start, per-request) and destroyed (request complete, plugin unload).

3. **Callback ordering**: The precise order in which callbacks are invoked during normal operation.

4. **Root vs. HTTP contexts**: The distinction between plugin-level (root) and request-level (HTTP) contexts.

5. **Resource cleanup**: How `onDone` and `onDelete` / `Drop` are used for cleanup before destruction.

## Use Cases

- **Learning tool**: Understand the Proxy-WASM execution model.
- **Debugging**: Diagnose callback ordering issues or lifecycle problems.
- **Plugin template**: Base for more complex plugins that need lifecycle hooks.
- **Performance analysis**: Benchmark callback overhead (test includes `benchmark: true`).
- **Documentation**: Generate execution traces for plugin documentation.
