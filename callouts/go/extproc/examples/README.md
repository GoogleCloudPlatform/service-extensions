# Go Callout Samples

This directory contains a collection of example ext_proc callout services written in Go, demonstrating various use cases, patterns, and best practices for building Envoy External Processing services. Each sample implements one or more HTTP processing phases and includes detailed documentation.

## Getting Started

Each sample directory contains:
- **Source code** (`*.go`)
- **README.md** with detailed documentation

## Quick Reference

### Core Infrastructure

| Sample | Description |
|--------|-------------|
| [server](internal/server/) | Core gRPC server infrastructure: `CalloutServer`, `GRPCCalloutService`, `HandlerRegistry`, TLS, health check |
| [utils](pkg/utils/) | Shared mutation helpers: header, body, immediate response, and dynamic forwarding metadata builders |

### Body Manipulation

| Sample | Description |
|--------|-------------|
| [add_body](samples/add_body/) | Replaces request body with `"new-body-request"` and response body with `"new-body-response"` |

### Header Manipulation

| Sample | Description |
|--------|-------------|
| [add_header](samples/add_header/) | Injects `header-request: Value-request` into requests and `header-response: Value-response` into responses |

### Routing & Traffic Management

| Sample | Description |
|--------|-------------|
| [dynamic_forwarding](samples/dynamic_forwarding/) | Routes requests to a backend IP extracted from the `ip-to-return` header, with a hardcoded fallback |
| [redirect](samples/redirect/) | Returns an unconditional `301 Moved Permanently` to `http://service-extensions.com/redirect` |

### Authentication & Authorization

| Sample | Description |
|--------|-------------|
| [jwt_auth](samples/jwt_auth/) | Validates RSA-signed JWT Bearer tokens and forwards decoded claims as `decoded-<claim>` headers |

### Reference Implementations

| Sample | Description |
|--------|-------------|
| [basic_callout_server](samples/basic_callout_server/) | Full four-phase reference implementation: injects headers and replaces bodies in all phases |
| [grpc_client_server](samples/grpc_client_server/) | Self-contained gRPC client-server demo for testing ext_proc interactions locally |

## Build

Build all samples from the repository root:
```bash
go build ./callouts/go/extproc/...
```

Build a specific sample:
```bash
go build ./callouts/go/extproc/samples/<sample_name>/...
```

## Test

Run all tests:
```bash
go test ./callouts/go/extproc/...
```

Run tests for a specific sample:
```bash
go test ./callouts/go/extproc/samples/<sample_name>/...

# With verbose output
go test -v ./callouts/go/extproc/samples/<sample_name>/...
```

## Additional Resources

- [Envoy ext_proc documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/ext_proc_filter)
- [go-control-plane](https://github.com/envoyproxy/go-control-plane)
- [service-extensions repository](https://github.com/GoogleCloudPlatform/service-extensions)