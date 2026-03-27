# Basic Callout Server (Java)

This callout server demonstrates a complete example of HTTP request and response
manipulation using a gRPC-based service callout. It combines both **header** and
**body** mutations across request and response flows in a Layer 7 load balancer.

The server showcases how to:
- Add and remove headers
- Control route cache behavior
- Append to request bodies
- Replace response bodies

Use this callout when you need a **full reference implementation** or want to
combine multiple transformation patterns in a single service.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `onRequestHeaders` callback:
   - Adds headers:
     - `request-header: added-request`
     - `c: d`
   - Clears the route cache to ensure routing decisions consider the new headers.
3. The load balancer sends a `ProcessingRequest` with `request_body`.
4. The server's `onRequestBody` callback:
   - Appends `-added-body` to the existing request body.
5. The request continues to the backend service with updated headers and body.
6. When the backend responds, the load balancer sends a `ProcessingRequest`
   with `response_headers`.
7. The server's `onResponseHeaders` callback:
   - Adds headers:
     - `response-header: added-response`
     - `c: d`
   - Removes the `foo` header if present.
   - Does not clear the route cache.
8. The load balancer sends a `ProcessingRequest` with `response_body`.
9. The server's `onResponseBody` callback:
   - Replaces the entire response body with `body replaced`.
10. The modified response is returned to the client.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `onRequestHeaders` | Adds headers and clears route cache. |
| `onRequestBody` | Appends `-added-body` to the request body. |
| `onResponseHeaders` | Adds headers and removes `foo` header. |
| `onResponseBody` | Replaces response body with `body replaced`. |

---

## Run

Start the callout server with default configuration:
```bash
# Maven
mvn exec:java -Dexec.mainClass="example.BasicCalloutServer"

# JAR
java -cp target/your-artifact.jar example.BasicCalloutServer
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=BasicCalloutServer

This example may also be covered by shared gRPC integration tests depending on
the repository setup.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request header mutation** | Adds `request-header: added-request` and `c: d`; clears route cache. |
| **Request body mutation** | Appends `-added-body` to the original request body. |
| **Response header mutation** | Adds `response-header: added-response` and `c: d`; removes `foo`. |
| **Response body mutation** | Replaces response body with `body replaced`. |
| **Combined transformations** | Demonstrates full request/response lifecycle mutation. |

---

## Available Languages

- [x] [Java](.) (this directory)
- [ ] Python
- [ ] Go