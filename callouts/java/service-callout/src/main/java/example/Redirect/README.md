# Redirect Callout (Java)

This callout server demonstrates how to perform an HTTP redirect using a gRPC-based
service callout in Java. It short-circuits normal request processing and returns
an immediate response to the client with a redirect status and location.

The server intercepts request headers and responds with a `301 Moved Permanently`
status, instructing the client to navigate to a different URL via the `Location`
header.

Use this callout when you need **URL redirection**, **traffic migration**, or
**request short-circuiting** without forwarding the request to a backend service.

---

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `onRequestHeaders` callback is triggered.
3. Instead of forwarding the request, the server builds an `ImmediateResponse`.
4. The response includes:
   - HTTP status code `301 (Moved Permanently)`
   - A `Location` header pointing to the redirect target
5. The load balancer immediately returns this response to the client, bypassing
   any backend service.

---

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `onRequestHeaders` | Returns an immediate 301 redirect response with a `Location` header. |

---

## Run

Start the callout server with default configuration:
```bash
# Maven
mvn exec:java -Dexec.mainClass="example.Redirect"

# JAR
java -cp target/your-artifact.jar example.Redirect
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=RedirectTest`

This example may also be covered by shared gRPC integration tests depending on
the repository setup.

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Any incoming request** | The request is not forwarded to a backend. |
| **Redirect response** | The client receives a `301 Moved Permanently` response. |
| **Location header** | The response includes `Location: http://service-extensions.com/redirect`. |
| **Immediate response** | Processing is short-circuited and handled entirely by the callout. |

---

## Available Languages

- [x] [Java](.) (this directory)
- [ ] Python
- [ ] Go