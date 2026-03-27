# Add Body Callout

This callout server demonstrates how to modify HTTP request and response bodies
using a gRPC-based service callout. It showcases both **appending to a request
body** and **replacing a response body** in a Layer 7 load balancer.

On incoming requests, the server appends a suffix to the existing body. On
outgoing responses, it replaces the body entirely with a static value.

Use this callout when you need **payload transformation**, **content injection**,
or **response rewriting** without modifying backend services.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_body` to the callout server.
2. The server's `onRequestBody` callback:
   - Reads the incoming request body.
   - Appends `-added-body` to the existing content.
   - Returns the modified body without clearing the original content.
3. The request continues to the backend service with the updated body.
4. When the backend responds, the load balancer sends a `ProcessingRequest`
   with `response_body`.
5. The server's `onResponseBody` callback:
   - Replaces the entire response body with the static value `body replaced`.
6. The modified response is returned to the client.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `onRequestBody` | Appends `-added-body` to the incoming request body. |
| `onResponseBody` | Replaces the response body with `body replaced`. |

---

## Run

Start the callout server with default configuration:
```bash
# Maven
mvn exec:java -Dexec.mainClass="example.AddBody"

# JAR
java -cp target/your-artifact.jar example.AddBody
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=AddBodyTest

This example may also be covered by shared gRPC integration tests depending on
the repository setup.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request body modification** | Incoming request body is appended with `-added-body`. |
| **Response body replacement** | Outgoing response body is replaced with `body replaced`. |
| **Partial mutation (request)** | Original request body is preserved and extended. |
| **Full mutation (response)** | Original response body is completely replaced. |
| **Payload transformation** | Enables dynamic request/response content manipulation. |

---

## Available Languages

- [x] [Java](.) (this directory)
- [x] Python
- [x] Go