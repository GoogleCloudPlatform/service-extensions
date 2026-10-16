# JWT Auth Callout (Java)

This callout server demonstrates how to perform JWT (JSON Web Token)
authentication using a gRPC-based service callout in Java. It validates tokens
from incoming HTTP requests and propagates decoded claims as headers for
downstream services.

The server extracts the JWT from the `Authorization` header, validates it using
an RSA public key loaded from a PEM file, and conditionally mutates headers
based on the validation result. Invalid or missing tokens result in request denial.

Use this callout when you need **authentication enforcement**, **JWT validation**,
or **identity propagation** in a Layer 7 load balancer.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server extracts the JWT from the `Authorization` header (Bearer token).
3. The token is validated using an RSA public key loaded from `certs/publickey.pem`.
4. If the token is valid:
   - The JWT claims are decoded.
   - Each claim is transformed into a header (e.g., `decoded-sub`, `decoded-name`).
   - The route cache is cleared to ensure routing decisions consider the new headers.
5. If the token is missing or invalid:
   - The request is denied with an error message.
6. The modified request (or denial response) is returned to the client.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `onRequestHeaders` | Extracts and validates JWT. On success, adds decoded claims as headers and clears route cache. On failure, denies the request. |

---

## Run

Start the callout server with default configuration:
```bash
# Maven
mvn exec:java -Dexec.mainClass="example.JwtAuth"

# JAR
java -cp target/your-artifact.jar example.JwtAuth
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=JwtAuthTest

This example may also be covered by shared gRPC integration tests depending on
the repository setup.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Valid JWT token** | Token is decoded and claims are added as headers (e.g., `decoded-sub`, `decoded-name`). |
| **Missing Authorization header** | Request is denied due to missing token. |
| **Invalid JWT token** | Request is denied with message "Authorization token is invalid". |
| **Header propagation** | All decoded JWT claims are forwarded as request headers. |
| **Route recalculation** | Route cache is cleared after successful validation. |

---

## Available Languages

- [x] [Java](.) (this directory)
- [ ] Python
- [ ] Go