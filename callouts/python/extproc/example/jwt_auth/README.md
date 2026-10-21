# JWT Validation Callout

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

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server extracts the JWT from the `Authorization` header (Bearer token).
3. The token is validated using a configured public key and algorithm (e.g., RS256).
4. If the token is valid:
   - The payload is decoded.
   - Each claim is transformed into a header (e.g., `decoded-name: John Doe`).
   - The route cache is cleared to ensure routing decisions consider the new headers.
5. If the token is missing or invalid:
   - The request is denied with an appropriate error message.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Extracts and validates JWT. On success, adds decoded claims as headers and clears route cache. On failure, denies the request. |

---

## Run

```bash
cd callouts/python
python -m extproc.example.jwt_validation.service_callout_example
```

---

## Test

```bash
cd callouts/python
pytest extproc/tests/basic_grpc_test.py
```

This example is covered by the shared gRPC integration tests rather than having
a dedicated test file.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Valid JWT token** | The token is successfully decoded, and its claims are added as headers (e.g., `decoded-sub`, `decoded-name`). Route cache is cleared. |
| **Missing Authorization header** | The request is denied with message "No Authorization token found." |
| **Invalid JWT token** | The request is denied with message "Authorization token is invalid." |
| **Header propagation** | All decoded JWT claims are forwarded as request headers for downstream services. |

---

## Available Languages

- [x] [Python](.) (this directory)
- [x] [Go](../../../../go/extproc/examples/jwt_validation/)
- [x] [Java](../../../../java/service-callout/src/main/java/example/JwtValidation.java)