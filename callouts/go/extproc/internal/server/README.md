# Callout Server Library

This package provides the core server infrastructure for building Envoy ext_proc callout services in Go. It defines the `CalloutServer` struct for managing gRPC server lifecycle (TLS, insecure, and health check), the `GRPCCalloutService` base struct that implements the `ExternalProcessorServer` interface with a handler dispatch loop, and the `HandlerRegistry` that maps each HTTP processing phase to a user-supplied function. Use this package as the foundation for every callout service — all sample plugins embed `GRPCCalloutService` and register handlers against its `HandlerRegistry` rather than implementing the gRPC interface directly.

## How It Works

1. A `CalloutServer` is created with a `Config` struct specifying addresses, TLS certificate paths, and feature flags.
2. If TLS is enabled and certificate paths are provided, the X.509 key pair is loaded at construction time via `tls.LoadX509KeyPair`.
3. The caller registers a `GRPCCalloutService` (or an embedding struct) with one or more handler functions populated on its `Handlers` field.
4. `StartGRPC` (TLS) and/or `StartInsecureGRPC` (plain TCP) are called — each binds a TCP listener, creates a `grpc.Server`, registers the service, enables gRPC reflection, and begins serving.
5. `StartHealthCheck` binds an HTTP server on the health check address and responds with `200 OK` to all requests, suitable for use with load balancer probes.
6. On each incoming ext_proc stream, `GRPCCalloutService.Process` reads `ProcessingRequest` messages in a loop and dispatches them to the appropriate registered handler based on the request variant (`RequestHeaders`, `ResponseHeaders`, `RequestBody`, `ResponseBody`, `RequestTrailers`, `ResponseTrailers`).
7. If a handler is registered for the incoming phase, its response is sent back over the stream. If no handler is registered for a phase, the message is silently ignored and the stream continues.
8. Any error returned by a handler terminates the stream.

## Server Methods

| Method | Purpose |
|---|---|
| `NewCalloutServer(config)` | Constructs a `CalloutServer`, loading TLS credentials if enabled |
| `StartGRPC(service)` | Starts a TLS-secured gRPC server on `Config.SecureAddress` |
| `StartInsecureGRPC(service)` | Starts a plain TCP gRPC server on `Config.InsecureAddress` |
| `StartHealthCheck()` | Starts an HTTP health check server on `Config.HealthCheckAddress` |

## Handler Registry

`HandlerRegistry` maps each ext_proc processing phase to a typed function. All fields are optional — unregistered phases are skipped silently.

| Field | Signature | Phase |
|---|---|---|
| `RequestHeadersHandler` | `func(*extproc.HttpHeaders) (*extproc.ProcessingResponse, error)` | Incoming request headers |
| `ResponseHeadersHandler` | `func(*extproc.HttpHeaders) (*extproc.ProcessingResponse, error)` | Outgoing response headers |
| `RequestBodyHandler` | `func(*extproc.HttpBody) (*extproc.ProcessingResponse, error)` | Incoming request body |
| `ResponseBodyHandler` | `func(*extproc.HttpBody) (*extproc.ProcessingResponse, error)` | Outgoing response body |
| `RequestTrailersHandler` | `func(*extproc.HttpTrailers) (*extproc.ProcessingResponse, error)` | Incoming request trailers |
| `ResponseTrailersHandler` | `func(*extproc.HttpTrailers) (*extproc.ProcessingResponse, error)` | Outgoing response trailers |

## Configuration

`Config` fields control all aspects of server startup:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `SecureAddress` | `string` | — | `host:port` for the TLS gRPC server |
| `InsecureAddress` | `string` | — | `host:port` for the plain TCP gRPC server |
| `HealthCheckAddress` | `string` | — | `host:port` for the HTTP health check endpoint |
| `CertFile` | `string` | — | Path to the TLS certificate file |
| `KeyFile` | `string` | — | Path to the TLS private key file |
| `EnableTLS` | `bool` | `false` | Enables the TLS gRPC server when `true` |
| `EnableInsecureServer` | `bool` | `false` | Enables the plain TCP gRPC server when `true` |

TLS certificates are only loaded when `EnableTLS` is `true` and both `CertFile` and `KeyFile` are non-empty. A failure to load certificates calls `log.Fatalf` and terminates the process.

## Key Code Walkthrough

- **`GRPCCalloutService.Process`** — The core dispatch loop. It calls `stream.Recv()` in a `for` loop, inspects the oneof variant of each `ProcessingRequest` using `req.Get*()` accessors, and invokes the corresponding handler if one is registered. Responses are sent immediately after each handler returns. The loop exits on any `stream.Recv()` error (including `io.EOF`).

- **Default handlers** — `GRPCCalloutService` provides no-op default implementations for all six phases, each returning an empty response of the appropriate type. These are not registered automatically; they exist as convenience methods that embedding structs can call explicitly if pass-through behaviour is desired.

- **gRPC reflection** — Both `StartGRPC` and `StartInsecureGRPC` call `reflection.Register(grpcServer)`, enabling tools like `grpcurl` to introspect the server's service definitions at runtime without a compiled proto descriptor.

- **Health check** — `StartHealthCheck` uses the standard `net/http` package to serve a single route (`/`) that unconditionally returns `200 OK`. It is designed to run in a goroutine alongside the gRPC servers.

## Build

Build the server package from the repository root:
```bash
# Go
go build ./callouts/go/extproc/internal/server/...
```

## Test

Run the unit tests for the server package:
```bash
# Run all tests in the server package
go test ./callouts/go/extproc/internal/server/...

# With verbose output
go test -v ./callouts/go/extproc/internal/server/...
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Registered handler is invoked** | `ProcessingRequest` for a phase with a registered handler | Handler called; `ProcessingResponse` sent over stream |
| **Unregistered phase is skipped** | `ProcessingRequest` for a phase with no handler | Message ignored; stream continues without sending a response |
| **Handler returns error** | Handler function returns a non-nil error | Stream terminated; error propagated to Envoy |
| **TLS enabled, certs valid** | `EnableTLS: true` with valid cert and key paths | TLS gRPC server started on `SecureAddress` |
| **TLS enabled, certs missing** | `EnableTLS: true` with invalid paths | `log.Fatalf` at construction; process exits |
| **TLS disabled** | `EnableTLS: false` | `StartGRPC` returns immediately without binding |
| **Insecure server disabled** | `EnableInsecureServer: false` | `StartInsecureGRPC` returns immediately without binding |
| **Health check probe** | HTTP `GET /` to `HealthCheckAddress` | `200 OK` with empty body |

## Available Languages

- [x] [Go](server.go)