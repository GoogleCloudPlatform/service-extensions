# Testing Example Plugin

This plugin is a **comprehensive testing demonstration** that showcases the full capabilities of the Proxy-WASM testing framework. It demonstrates various testing techniques including header validation, logging verification, time control, immediate responses, and multiple input formats (proto, inline content, and external files). Use this plugin as a reference when writing tests for your own plugins. It operates during both the **request headers** and **response headers** processing phases.

## How It Works

### Core Functionality

1. **Request headers phase**:
   - Logs a debug message with the context ID
   - Includes commented-out code for dumping all request headers (useful for debugging)
   - Continues processing normally

2. **Response headers phase**:
   - Logs a debug message with the context ID
   - Emits three timestamps to demonstrate time-based testing
   - Checks for a special header `reply-with-error`
   - If `reply-with-error` header exists, sends a 500 error response
   - Otherwise, continues processing normally

### Testing Capabilities Demonstrated

The plugin's test suite (`tests.textpb`) demonstrates:

1. **Header assertions**: Positive and negative header matching
2. **Log verification**: Regex-based log message validation
3. **Time control**: Frozen time for deterministic timestamp testing
4. **Immediate responses**: Testing local response generation
5. **Multiple input formats**:
   - Proto format (structured headers)
   - Inline HTTP/1.1 content (string-based)
   - External file content (file references)
6. **HTTP/1.1 parsing**: Origin form, absolute form, request/response formats

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Logs context ID for debugging |
| `on_http_response_headers` | Emits timestamps and conditionally sends error response |

## Key Code Walkthrough

### C++ Implementation

- **Debug logging**:
  ```cpp
  LOG_DEBUG(std::string("request headers ") + std::to_string(id()));
  ```
  Logs the context ID for each request (helpful for debugging concurrent requests).

- **Header debugging (commented)**:
  ```cpp
  auto result = getRequestHeaderPairs();
  auto pairs = result->pairs();
  for (auto& p : pairs) {
      LOG_INFO(std::string(p.first) + " -> " + std::string(p.second));
  }
  ```
  Can be uncommented to dump all headers to logs for troubleshooting.

- **Timestamp emission**:
  ```cpp
  for (int i = 1; i <= 3; ++i) {
      using namespace std::chrono_literals;
      const auto ts = std::chrono::high_resolution_clock::now();
      const auto ns = ts.time_since_epoch() / 1ns;
      LOG_INFO("time " + std::to_string(i) + ": " + std::to_string(ns));
  }
  ```
  Emits three timestamps in nanoseconds. In tests with `time_secs: 123456789`, these timestamps are frozen for deterministic testing.

- **Conditional error response**:
  ```cpp
  if (getResponseHeader("reply-with-error")->data()) {
      sendLocalResponse(500, "extra", "fake error", {{"error", "goaway"}});
      return FilterHeadersStatus::StopAllIterationAndWatermark;
  }
  ```
  Sends a 500 error if the special header is present.

### Rust Implementation

- **Timestamp emission**:
  ```rust
  for i in 1..4 {
      let ns = SystemTime::now()
          .duration_since(SystemTime::UNIX_EPOCH)
          .unwrap()
          .as_nanos();
      info!("time {}: {}", i, ns);
  }
  ```
  Equivalent timestamp logic using Rust's `SystemTime`.

- **Conditional error response**:
  ```rust
  if self.get_http_response_header("reply-with-error").is_some() {
      self.send_http_response(500, vec![("error", "goaway")], Some(b"fake error"));
      return Action::Pause;
  }
  ```

## Test Configuration

The test file demonstrates advanced testing features:

### Environment Configuration

```protobuf
env {
  log_level: DEBUG          # Set log level for verbose output
  log_path: "/dev/stdout"   # Direct logs to stdout
  time_secs: 123456789      # Freeze time for deterministic tests
}
```

**Time control**: Setting `time_secs` freezes the system clock, making all timestamp-based operations deterministic. Perfect for testing time-dependent behavior.

### Test 1: Headers_Proto (Structured Headers)

Demonstrates proto-based header input:

```protobuf
request_headers {
  input {
    header { key: ":path" value: "/" }
    header { key: ":method" value: "GET" }
  }
  result {
    has_header { key: ":method" value: "GET" }      # Positive match
    no_header { key: ":scheme" }                     # Negative match
    log { regex: ".*request headers.*" }             # Log presence
    log { regex: ".*response headers.*" invert: true }  # Log absence
  }
}
```

**Response testing**:
```protobuf
response_headers {
  input {
    header { key: "reply-with-error" value: "yes" }
  }
  result {
    immediate { http_status: 500 }              # Check status
    body { exact: "fake error" }                # Check body
    has_header { key: "error" value: "goaway" } # Check added header
    no_header { key: "server-message" }         # Original header removed
    log { regex: ".*time 1: 123456789000000000" }  # Frozen time
  }
}
```

### Test 2: Headers_Content (Inline HTTP/1.1)

Demonstrates inline HTTP/1.1 content:

```protobuf
request_headers {
  input {
    content:
      "GET /my/path?foo=bar HTTP/1.1\n"
      "Host: myhost.com\n"
      "MyHeader: MyVal1\n"
      "MyHeader: MyVal2\n"
  }
  result {
    has_header { key: ":method" value: "GET" }
    has_header { key: ":path" value: "/my/path?foo=bar" }
    has_header { key: ":authority" value: "myhost.com" }
    no_header { key: "Host" }  # Host converted to :authority
    has_header { key: "MyHeader" value: "MyVal1, MyVal2" }  # Duplicate headers combined
  }
}
```

**HTTP/1.1 → HTTP/2 conversion**:
- `Host:` header becomes `:authority` pseudo-header
- Duplicate headers are combined with `, ` separator
- Request line is parsed into `:method`, `:path`, and optionally `:scheme`

### Test 3: Headers_File (External File)

Demonstrates file-based input:

```protobuf
request_headers {
  input {
    file: "request_headers.data"
  }
  result {
    has_header { key: ":scheme" value: "https" }
    has_header { key: ":authority" value: "example.com:8080" }
  }
}
```

**File content** (`request_headers.data`):
```http
GET https://example.com:8080/my/path?foo=bar HTTP/1.1
Host: myhost.com
MyHeader: MyVal1
MyHeader: MyVal2
```

**Absolute form parsing**: The absolute URI in the request line is parsed into `:scheme` and `:authority`.

## Configuration

No configuration required. This is a testing demonstration plugin.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/testing:plugin_rust.wasm

# C++
bazelisk build //samples/testing:plugin_cpp.wasm
```

**Note**: Only C++ and Rust implementations are available (no Go version).

## Test

Run the comprehensive test suite:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/testing/tests.textpb \
    --plugin /mnt/bazel-bin/samples/testing/plugin_rust.wasm

# Using Bazel (both languages)
bazelisk test --test_output=all //samples/testing:tests
```

## Expected Behavior

The test suite validates:

| Test | Purpose | Key Validations |
|------|---------|----------------|
| **Headers_Proto** | Structured header input | Header matching, log verification, frozen time, immediate response |
| **Headers_Content** | Inline HTTP/1.1 input | Request parsing, header conversion, duplicate header handling |
| **Headers_File** | External file input | Absolute form parsing, file loading |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [ ] Go (not available)

## Testing Features Reference

### Header Assertions

**Positive matches**:
```protobuf
has_header { key: ":method" value: "GET" }
headers { exact: ":method: GET" }
```

**Negative matches**:
```protobuf
no_header { key: ":scheme" }
headers { regex: ":scheme:.*" invert: true }
```

### Log Assertions

**Presence**:
```protobuf
log { regex: ".*request headers.*" }
```

**Absence**:
```protobuf
log { regex: ".*response headers.*" invert: true }
```

### Immediate Response Testing

```protobuf
result {
  immediate { http_status: 500 }
  body { exact: "fake error" }
  has_header { key: "error" value: "goaway" }
}
```

### Input Formats

**1. Proto format**:
```protobuf
input {
  header { key: ":path" value: "/" }
  header { key: ":method" value: "GET" }
}
```

**2. Inline content**:
```protobuf
input {
  content:
    "GET /path HTTP/1.1\n"
    "Host: example.com\n"
}
```

**3. External file**:
```protobuf
input {
  file: "request_headers.data"
}
```

## Best Practices for Plugin Testing

1. **Test positive and negative cases**: Use both `has_header` and `no_header`
2. **Verify logs**: Use regex to check log output
3. **Freeze time**: Set `time_secs` for deterministic time-based tests
4. **Test immediate responses**: Validate status, body, and headers
5. **Use multiple input formats**: Proto for structure, content for realism, files for reuse
6. **Test header transformations**: Verify HTTP/1.1 → HTTP/2 conversion
7. **Test error paths**: Include tests that trigger error conditions

## Common Testing Patterns

**Test header addition**:
```protobuf
input { header { key: "X-Input" value: "test" } }
result { has_header { key: "X-Output" value: "modified" } }
```

**Test header removal**:
```protobuf
input { header { key: "X-Remove" value: "this" } }
result { no_header { key: "X-Remove" } }
```

**Test logging**:
```protobuf
result { log { regex: ".*expected log message.*" } }
```

**Test immediate response**:
```protobuf
result {
  immediate { http_status: 403 }
  body { exact: "Access denied" }
}
```

This plugin serves as the **definitive testing reference** for Proxy-WASM plugins!