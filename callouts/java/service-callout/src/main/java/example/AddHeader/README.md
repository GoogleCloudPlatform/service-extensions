# Add Header Callout (Java)

This callout server demonstrates how to modify HTTP request and response headers
using a gRPC-based service callout in Java. It showcases adding, removing, and
managing headers while optionally controlling the route cache in a Layer 7 load balancer.

On incoming requests, the server adds new headers and clears the route cache. On
outgoing responses, it adds new headers and removes specific ones without
affecting the route cache.

Use this callout when you need **header enrichment**, **header cleanup**, or
**routing influence via headers** without modifying backend services.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `onRequestHeaders` callback:
   - Adds headers:
     - `request-header: added-request`
     - `c: d`
   - Clears the route cache to ensure routing decisions consider the new headers.
3. The request continues to the backend service with updated headers.
4. When the backend responds, the load balancer sends another `ProcessingRequest`
   with `response_headers`.
5. The server's `onResponseHeaders` callback:
   - Adds headers:
     - `response-header: added-response`
     - `c: d`
   - Removes the `foo` header if present.
   - Does not clear the route cache.
6. The modified response is returned to the client.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `onRequestHeaders` | Adds headers (`request-header`, `c`) and clears route cache. |
| `onResponseHeaders` | Adds headers (`response-header`, `c`) and removes `foo` header. |

---

## Run

Start the callout server with default configuration:
```bash
# Maven
mvn exec:java -Dexec.mainClass="example.AddHeader"

# JAR
java -cp target/your-artifact.jar example.AddHeader
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=AddHeaderTest

This example may also be covered by shared gRPC integration tests depending on
the repository setup.
```
---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request header addition** | Adds `request-header: added-request` and `c: d` to incoming requests. |
| **Response header addition** | Adds `response-header: added-response` and `c: d` to outgoing responses. |
| **Response header removal** | Removes `foo` header if present in the response. |
| **Route recalculation (request)** | Route cache is cleared after request mutation. |
| **No route change (response)** | Route cache remains unchanged during response mutation. |

---

## Available Languages

- [x] [Java](.) (this directory)
- [ ] Python
- [ ] Go