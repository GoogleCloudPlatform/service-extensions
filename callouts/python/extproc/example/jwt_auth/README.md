# JWT Auth Plugin (Python)

This plugin implements JWT authentication at the proxy layer by intercepting incoming request headers, validating a Bearer token against an RSA public key loaded from disk, and forwarding the decoded claims as individual headers to the upstream service. Requests carrying an invalid, malformed, or missing token are denied before reaching the backend. Use this plugin when you need to enforce token-based authentication and propagate verified identity claims to upstream services without modifying application logic. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler iterates over all request headers looking for the `Authorization` header (case-insensitive match on `header.key.lower()`).
3. The raw value is decoded as UTF-8, stripped of whitespace, and split on spaces — the last token is taken as the JWT, handling both `Bearer <token>` and bare token formats.
4. If no `Authorization` header is found, `deny_callout` is called with `"No Authorization token found."` and the request is rejected.
5. The extracted token is decoded using `jwt.decode` with the RS256 algorithm and the RSA public key loaded at startup from `./extproc/ssl_creds/publickey.pem`.
6. If decoding raises an `InvalidTokenError`, `None` is returned and the handler calls `deny_callout` with `"Authorization token is invalid."`.
7. If the token is valid, all decoded claims are prefixed with `"decoded-"` and injected as new request headers, and the route cache is cleared to force Envoy to recompute routing.
8. The modified request with claim headers is forwarded to the upstream service.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_headers` | Validates the JWT Bearer token and injects decoded claims as headers, or denies the request on failure |

## Key Code Walkthrough

- **Class structure** — `CalloutServerExample` extends `callout_server.CalloutServer` and overrides `__init__` to load the RSA public key at startup via `_load_public_key`. Only the request headers callback is registered; all other phases pass through unmodified. The server accepts command-line arguments at startup via `add_command_line_args()`.

- **Public key loading** — `_load_public_key(path)` opens the PEM file in binary mode and stores the raw bytes as `self.public_key`. The path defaults to `./extproc/ssl_creds/publickey.pem`. A missing or unreadable file raises an `IOError` at startup, preventing the server from running with an invalid key.

- **Token extraction** — `extract_jwt_token` uses a generator expression to iterate over `request_headers.headers.headers`, matching on `header.key.lower() == 'authorization'` for a case-insensitive comparison and decoding `header.raw_value` as UTF-8 (falling back to `header.value`). `next(..., None)` returns `None` if no matching header exists. The result is stripped and split on spaces, with the last element taken as the token — this handles both `Bearer <token>` and bare token values.

- **Token validation** — `validate_jwt_token` calls `extract_jwt_token` first, denying immediately if the result is `None`. If a token is found, `jwt.decode(jwt_token, key, algorithms=[algorithm])` validates the signature against the RSA public key with the RS256 algorithm. A successful decode is logged at `INFO` level and the claims dict is returned. Any `InvalidTokenError` is caught and `None` is returned silently, with the caller responsible for denial.

- **Claims forwarding** — In `on_request_headers`, a non-`None` decoded result is iterated as `decoded.items()`, prefixing each key with `"decoded-"` and converting values to strings. The resulting list is passed to `callout_tools.add_header_mutation` with `clear_route_cache=True`, injecting all claims as new request headers and forcing Envoy to recompute its routing decision.

- **Request denial** — If `validate_jwt_token` returns `None`, `on_request_headers` calls `callout_tools.deny_callout(context, 'Authorization token is invalid.')` to close the connection. Denial can also occur inside `validate_jwt_token` itself when no token is found, meaning denial may happen at two distinct points depending on the failure mode.

- **Command-line arguments** — The `__main__` block uses `add_command_line_args().parse_args()` and passes the result as keyword arguments to `CalloutServerExample(**vars(args))`, allowing server address, port, and TLS settings to be configured at runtime.

## Configuration

The RSA public key path is the only startup-time configuration, hardcoded in `__init__`:

- Default public key path: `./extproc/ssl_creds/publickey.pem`
- JWT signing algorithm: `RS256`
- Claim header prefix: `"decoded-"`
- Request phase route cache: cleared on valid token (`True`)

A sample valid RS256 token for testing is provided in the class docstring.

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt

# Additional JWT dependency
pip install PyJWT cryptography
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.jwt_auth
```

Or run directly, optionally passing command-line arguments:
```bash
# Default configuration
python jwt_auth.py

# Custom address and port
python jwt_auth.py --address 0.0.0.0 --port 8443
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the jwt_auth sample
python -m pytest tests/jwt_auth_test.py

# With verbose output
python -m pytest -v tests/jwt_auth_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Valid token, claims forwarded** | `Authorization: Bearer <valid-rs256-jwt>` | `decoded-<claim>: <value>` headers added for each claim; route cache cleared |
| **Missing Authorization header** | Request with no `Authorization` header | Request denied with `"No Authorization token found."` |
| **Invalid JWT signature** | `Authorization: Bearer <tampered-jwt>` | `InvalidTokenError` caught; request denied with `"Authorization token is invalid."` |
| **Expired token** | `Authorization: Bearer <expired-jwt>` | `InvalidTokenError` caught; request denied with `"Authorization token is invalid."` |
| **Bare token (no Bearer prefix)** | `Authorization: <token>` | Last whitespace-split token used; validated normally if signature matches |
| **PEM file missing at startup** | `./extproc/ssl_creds/publickey.pem` not found | `IOError` raised at construction; server fails to start |
| **Response phases** | Any HTTP response | All response phases pass through unmodified; no response callbacks registered |

## Available Languages

- [x] [Go](JwtAuth.go)
- [x] [Java](JwtAuth.java)
- [x] [Python](jwt_auth.py)