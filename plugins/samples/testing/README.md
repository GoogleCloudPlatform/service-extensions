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

## Implementation Notes

- **Console debugging**: Implements intentional logging logic strictly to record and output context IDs and operational timestamps. 
- **Time precision**: Intentionally forces absolute timestamp execution in rust using `SystemTime` and C++ via `<chrono>` to enable locked tests.
- **Fault injection**: Monitors the specified error request header and deliberately disrupts processing by transmitting a hardcoded 500 error HTTP response locally.

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

| Scenario | Description |
|---|---|
| **Headers_Proto** | Verifies execution behaviors like header matching, frozen logs, and immediate response outputs using structured input properties. |
| **Headers_Content** | Verifies advanced request parsing capabilities handling duplicate headers directly from inline HTTP/1.1 input formats. |
| **Headers_File** | Verifies logic surrounding external file loading functionality and interpreting raw HTTP absolute URI components. |

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