# Proxy-WASM Plugin Samples

This directory contains a collection of example Proxy-WASM plugins demonstrating various use cases, patterns, and best practices for plugin development. Each sample includes implementations in one or more languages (C++, Go, Rust) along with comprehensive tests and documentation.

## Getting Started

Each plugin directory contains:
- **Source code** (`plugin.cc`, `plugin.go`, `plugin.rs`)
- **README.md** with detailed documentation
- **tests.textpb** with test cases
- **BUILD** file for compilation

## Quick Reference

### Authentication & Authorization

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [block_request](block_request/) | Blocks requests based on presence of authentication token in query parameters | C++, Rust |
| [config_denylist](config_denylist/) | Blocks requests from tokens listed in a configuration file (denylist) | C++, Rust |
| [hmac_authcookie](hmac_authcookie/) | Validates HMAC authentication tokens from cookies | C++ |
| [hmac_authtoken](hmac_authtoken/) | Validates HMAC authentication tokens from URL query parameters | C++ |
| [hmac_token_validation](hmac_token_validation/) | Validates HMAC tokens from Authorization header | C++ |
| [jwt_auth](jwt_auth/) | Validates JWT tokens from URL query parameters using RSA public key | C++, Go |

### Request Modification

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [add_request_header](add_request_header/) | Adds a custom header to incoming requests | C++, Go, Rust |
| [normalize_header](normalize_header/) | Detects device type and adds normalized client-device-type header | C++, Go, Rust |
| [overwrite_header](overwrite_header/) | Conditionally replaces request headers and unconditionally sets response headers | C++, Go, Rust |
| [redirect](redirect/) | Redirects requests based on path prefix matching with 301 responses | C++, Go, Rust |
| [redirect_bulk](redirect_bulk/) | Redirects multiple domains based on configuration file mappings | C++, Go, Rust |
| [regex_rewrite](regex_rewrite/) | Rewrites URL paths using regular expression pattern matching | C++, Go, Rust |
| [set_query](set_query/) | Adds or replaces query parameters in request URLs | C++, Rust |

### Response Modification

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [add_custom_response](add_custom_response/) | Adds custom headers to HTTP responses based on conditions | C++, Go, Rust |
| [add_device_type](add_device_type/) | Adds device type information to response headers | C++, Go, Rust |
| [add_response_header](add_response_header/) | Adds a custom header to outgoing responses | C++, Go, Rust |
| [content_injection](content_injection/) | Injects script tags into HTML response bodies | Rust |
| [error_page_with_traceid](error_page_with_traceid/) | Generates custom error pages with trace IDs for debugging | C++ |
| [html_domain_rewrite](html_domain_rewrite/) | Rewrites domain names in HTML anchor tags | Rust |
| [overwrite_errcode](overwrite_errcode/) | Remaps 5xx server error codes to different status codes | C++, Go, Rust |
| [remove_cookie](remove_cookie/) | Removes all Set-Cookie headers from responses | C++, Go, Rust |
| [set_cookie](set_cookie/) | Automatically creates session cookies for requests without existing sessions | C++ |

### Routing & Traffic Management

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [ab_testing](ab_testing/) | Implements A/B testing by routing users to different backends | C++, Go, Rust |
| [geo_directional_origin](geo_directional_origin/) | Routes requests to different origins based on geographic location | Go |

### Security & Validation

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [check_pii](check_pii/) | Detects and blocks requests containing personally identifiable information (PII) | C++, Go |
| [enable_recaptcha](enable_recaptcha/) | Injects Google reCAPTCHA v3 script into HTML pages | Rust |

### Logging & Debugging

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [local_reply](local_reply/) | Sends immediate local responses without contacting upstream servers | C++, Go, Rust |
| [log_calls](log_calls/) | Logs all plugin lifecycle callbacks for debugging | C++, Rust |
| [log_query](log_query/) | Parses and logs specific query parameters from request URLs | C++, Go, Rust |

### Documentation & Learning

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [docs_first_plugin](docs_first_plugin/) | Introductory plugin demonstrating basic header manipulation | C++, Go, Rust |
| [docs_plugin_config](docs_plugin_config/) | Demonstrates plugin configuration loading and parsing | C++, Go, Rust |
| [testing](testing/) | Comprehensive testing framework demonstration with multiple input formats | C++, Rust |

### Advanced Examples

| Plugin | Description | Languages |
|--------|-------------|-----------|
| [body_chunking](body_chunking/) | Demonstrates request and response body processing with chunking | C++ |

## Language Support

### Choosing a Language

- **C++**: Best for performance-critical plugins, access to mature libraries (RE2, Abseil, Boost)
- **Go**: Best for rapid development, familiar syntax for Go developers
- **Rust**: Best for memory safety guarantees, modern language features

## Building Plugins

Build a specific plugin:
```bash
# C++
bazelisk build //samples/<plugin_name>:plugin_cpp.wasm

# Go
bazelisk build //samples/<plugin_name>:plugin_go.wasm

# Rust
bazelisk build //samples/<plugin_name>:plugin_rust.wasm
```

Build all plugins:
```bash
bazelisk build //samples/...
```

## Testing Plugins

Test a specific plugin:
```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/<plugin_name>/tests.textpb \
    --plugin /mnt/bazel-bin/samples/<plugin_name>/plugin_rust.wasm

# Using Bazel
bazelisk test --test_output=all //samples/<plugin_name>:tests
```

Test all plugins:
```bash
bazelisk test --test_output=all //samples/...
```

## Plugin Categories by Use Case

### API Gateway
- jwt_auth
- hmac_authtoken
- add_request_header
- overwrite_errcode
- remove_cookie

### Web Application Firewall
- check_pii
- block_request
- config_denylist

### CDN / Edge
- redirect_bulk
- content_injection
- html_domain_rewrite
- set_cookie

### Load Balancing
- ab_testing
- geo_directional_origin

### Observability
- log_calls
- log_query
- error_page_with_traceid

## Contributing

When adding new samples:
1. Include implementations in at least one language
2. Add comprehensive tests in `tests.textpb`
3. Create a detailed README.md
4. Follow existing code style and patterns
5. Update this index file

## Additional Resources

- [Proxy-WASM Specification](https://github.com/proxy-wasm/spec)
- [Proxy-WASM C++ SDK](https://github.com/proxy-wasm/proxy-wasm-cpp-sdk)
- [Proxy-WASM Go SDK](https://github.com/proxy-wasm/proxy-wasm-go-sdk)
- [Proxy-WASM Rust SDK](https://github.com/proxy-wasm/proxy-wasm-rust-sdk)
