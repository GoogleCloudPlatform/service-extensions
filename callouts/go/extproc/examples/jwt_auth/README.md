# JWT Auth Plugin

This plugin implements JWT authentication at the proxy layer by intercepting incoming request headers, validating a Bearer token against an RSA public key, and forwarding the decoded claims as individual headers to the upstream service. Requests carrying an invalid or missing token are rejected with a `PermissionDenied` gRPC status before reaching the backend. Use this plugin when you need to enforce token-based authentication and propagate verified identity claims to upstream services without modifying application logic. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `HandleRequestHeaders` handler.
2. The handler extracts the `Authorization` header and strips the `Bearer ` prefix if present.
3. The token is parsed and validated using `jwt-go` against an RSA public key loaded from a PEM file at startup.
4. If the token is missing, malformed, or fails signature validation, the handler returns a `PermissionDenied` gRPC error and the request is rejected.
5. If the token is valid, the handler iterates over the decoded JWT claims and constructs a list of `decoded-<claim>: <value>` headers.
6. Numeric claims `iat` and `exp` are formatted as plain integers (avoiding scientific notation from Go's default `float64` formatting).
7. The handler returns a `ProcessingResponse` that replaces the existing request headers with the decoded claim headers, clearing the original header set.

## Implementation Notes

- **Service structure**: `ExampleCalloutService` embeds `server.GRPCCalloutService` and adds a `PublicKey []byte` field to hold the RSA public key. The handler is registered in `NewExampleCalloutServiceWithKeyPath`, which also calls `LoadPublicKey` to read the PEM file from disk at startup. `NewExampleCalloutService` is a convenience constructor that defaults to `./extproc/ssl_creds/publickey.pem`.
- **Public key loading**: `LoadPublicKey` reads the PEM file using `ioutil.ReadFile` and stores the raw bytes on the service struct. A failure to load the key calls `log.Fatalf`, preventing the service from starting with an invalid or missing key.
- **Token extraction**: `extractJWTToken` iterates over `headers.Headers.Headers` and returns the raw value of the first header whose key matches `"Authorization"`. It returns an error if no such header exists.
- **Token validation**: `validateJWTToken` strips the `Bearer ` prefix if present, then calls `jwt.Parse` with a key function that enforces RSA signing (`*jwt.SigningMethodRSA`) and parses the public key with `jwt.ParseRSAPublicKeyFromPEM`. If the token is valid and the claims are of type `jwt.MapClaims`, the claims map is returned.
- **Claims forwarding**: `HandleRequestHeaders` iterates over the validated claims map and builds a `[]struct{ Key, Value string }` slice prefixing each claim name with `"decoded-"`. For `iat` and `exp` fields, the `float64` value is cast to `int64` and formatted with `%d` to prevent scientific notation like `1.7e+09`.
- **Header mutation**: The claims slice is passed to `utils.AddHeaderMutation` with `clear: true`, which replaces the entire incoming header set with only the decoded claim headers. This prevents raw JWT tokens from being forwarded to the upstream service.
- **Request rejection**: If `validateJWTToken` returns an error at any point, `HandleRequestHeaders` immediately returns `nil` and a `status.Errorf(codes.PermissionDenied, ...)` gRPC error, causing Envoy to return a `403` response to the client.

## Configuration

The only configurable parameter is the path to the RSA public key PEM file, provided at construction time:
- `default public key path`: `./extproc/ssl_creds/publickey.pem`
- `custom path`: pass an alternative path to `NewExampleCalloutServiceWithKeyPath(keyPath)`

All other behaviour — the header name, Bearer prefix stripping, claim name prefix, and integer formatting for `iat`/`exp` — is hardcoded in the handler.

## Build

Build the callout service from the repository root:
```bash
# Go
go build ./callouts/go/extproc/...
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests in the jwt_auth package
go test ./callouts/go/extproc/samples/jwt_auth/...

# With verbose output
go test -v ./callouts/go/extproc/samples/jwt_auth/...
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Valid token, claims forwarded** | Original headers are cleared and `decoded-<claim>: <value>` headers are added for each claim in the JWT. |
| **Valid token, numeric claims** | `decoded-iat` and `decoded-exp` are formatted as plain integers (e.g. `1700000000`), avoiding scientific notation. |
| **Missing Authorization header** | A request with no `Authorization` header is rejected with a `PermissionDenied` gRPC error. |
| **Invalid or expired token** | A request with `Authorization: Bearer <bad-jwt>` is rejected with a `PermissionDenied` gRPC error. |
| **Wrong signing algorithm** | A JWT signed with a non-RSA algorithm is rejected with a `PermissionDenied` gRPC error due to an unexpected signing method. |
| **Bearer prefix present** | The `Bearer ` prefix is stripped before parsing and the token is validated correctly. |
| **Bearer prefix absent** | The token is used as-is and validated correctly if the signature matches. |

## Available Languages

- [x] [Go](jwt_auth.go)
- [x] [Java](jwt_auth.java)
- [x] [Python](jwt_auth.py)
