# JWT Auth Callout (Go)

This callout server validates a JWT (JSON Web Token) from incoming HTTP request
headers and applies header mutations based on the decoded token payload. It
demonstrates how to enforce authentication and propagate identity data using
header transformations in a Layer 7 load balancer.

The server extracts the JWT from the `Authorization` header, validates it using
a configured public key and algorithm, and, if valid, injects decoded claims as
headers into the request. If the token is missing or invalid, the request is
denied.

Use this callout when you need **authentication enforcement**, **JWT validation**,
or **propagation of identity claims** to downstream services.

---

## How It Works

1. Extracts JWT from `Authorization` header.
2. Validates token using RSA public key.
3. On success:
   - Adds decoded claims as headers.
   - Clears route cache.
4. On failure:
   - Denies the request.

---

## Callbacks / Handlers

| Handler | Behavior |
|---|---|
| `HandleRequestHeaders` | Validates JWT and adds decoded claims as headers. |

---

## Run

```bash
cd callouts/go
EXAMPLE_TYPE=jwt_auth go run ./extproc/cmd/example/main.go
```

---

## Test

```bash
cd callouts/go
go test ./extproc/examples/jwt_auth/...
```

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Valid token** | Claims added as headers (`decoded-*`). |
| **Invalid token** | Request denied. |
| **Missing token** | Request denied. |

---

## Available Languages

- [x] [Go](.) (this directory)
- [ ] Python
- [ ] Java