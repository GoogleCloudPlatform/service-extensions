# gRPC Ext_Proc Client-Server Example

This sample demonstrates a self-contained gRPC client-server setup for the Envoy External Processing (ext_proc) protocol. It spins up a local gRPC server that implements the `ExternalProcessor` service, then connects to it as a client, sends a sequence of `ProcessingRequest` messages parsed from a JSON input, and logs the resulting `ProcessingResponse` messages. Use this sample when you need to test or prototype ext_proc interactions locally without a running Envoy proxy. It operates as a **standalone executable** covering the full request-response lifecycle over a bidirectional gRPC stream.

## How It Works

1. The program parses CLI flags for server address, TLS settings, and a JSON payload containing one or more `ProcessingRequest` objects.
2. A local gRPC server is started in a background goroutine, registering a dummy `ExternalProcessor` implementation that responds to every request with an empty `HeadersResponse`.
3. The main goroutine waits for the server to be ready, then establishes a gRPC client connection to the same address (plain TCP or TLS, depending on flags).
4. The JSON input is unmarshalled into a slice of `ProcessingRequest` protobuf messages using `protojson`.
5. A bidirectional streaming RPC (`Process`) is opened, and each request is sent over the stream in order.
6. The send side of the stream is closed to signal completion to the server.
7. The program collects all `ProcessingResponse` messages from the server until the stream closes, logging each one in protobuf text format.

## CLI Flags

| Flag | Default | Purpose |
|---|---|---|
| `--tls` | `false` | Enables TLS for the client connection if set to `true` |
| `--cert_file` | `""` | Path to the CA root certificate file (required when `--tls` is `true`) |
| `--addr` | `localhost:8181` | Server address in `host:port` format |
| `--data` | *(required)* | JSON string containing an array of `ProcessingRequest` objects |

## Key Code Walkthrough

- **Server implementation** — The `server` struct embeds `extproc.UnimplementedExternalProcessorServer` and overrides the `Process` method. It reads requests from the bidirectional stream in a loop, logs each one, and replies with a hardcoded `ProcessingResponse` wrapping an empty `RequestHeaders` response. This stub is intentionally minimal and serves only to demonstrate the server side of the protocol.

- **Server startup** — `startServer` binds a TCP listener, creates a bare `grpc.Server`, registers the `ExternalProcessor` implementation, and calls `Done` on a `sync.WaitGroup` before blocking on `Serve`. This allows the main goroutine to synchronize on server readiness before proceeding.

- **Channel creation** — `makeChannel` wraps `grpc.Dial` and selects either TLS credentials (loaded from the provided cert file) or `insecure.NewCredentials()` based on the `--tls` flag. This separation keeps connection setup testable and reusable.

- **JSON request dispatch** — `makeJSONRequest` unmarshals the raw JSON array into individual `json.RawMessage` entries, then uses `protojson.Unmarshal` to decode each one into a typed `*extproc.ProcessingRequest`. All requests are streamed to the server sequentially, the send side is closed with `stream.CloseSend()`, and responses are collected until `io.EOF`.

- **Response logging** — Each received `ProcessingResponse` is formatted with `prototext.Format` and written to the standard logger, producing human-readable protobuf text output for inspection.

## Configuration

All configuration is provided via CLI flags at runtime. No config files or environment variables are required. The only mandatory flag is `--data`, which must be a valid JSON array of `ProcessingRequest` objects.

## Build

Build the executable from the repository root:
```bash
# Go
go build ./callouts/go/extproc/samples/grpc_client_server/...
```

## Run

Start the sample with a minimal JSON payload:
```bash
# Plain TCP (default)
go run main.go --data '[{"requestHeaders": {"headers": {}}}]'

# Custom address
go run main.go --addr localhost:9090 --data '[{"requestHeaders": {"headers": {}}}]'

# With TLS
go run main.go --tls --cert_file /path/to/ca.crt --addr localhost:8443 \
    --data '[{"requestHeaders": {"headers": {}}}]'
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests in the grpc_client_server package
go test ./callouts/go/extproc/samples/grpc_client_server/...

# With verbose output
go test -v ./callouts/go/extproc/samples/grpc_client_server/...
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Single request is processed** | JSON array with one `ProcessingRequest` | One `ProcessingResponse` logged in protobuf text format |
| **Multiple requests are processed** | JSON array with N `ProcessingRequest` entries | N `ProcessingResponse` messages logged in order |
| **Stream closes cleanly** | All requests sent | `CloseSend` signals EOF; server loop exits on `io.EOF` |
| **Missing `--data` flag** | No `--data` argument provided | Program exits with `log.Fatal("Data JSON is required")` |
| **TLS disabled** | `--tls=false` (default) | Client connects with `insecure.NewCredentials()` over plain TCP |
| **TLS enabled** | `--tls=true` with valid `--cert_file` | Client connects using CA certificate for transport security |

## Available Languages

- [x] [Go](client.go)
