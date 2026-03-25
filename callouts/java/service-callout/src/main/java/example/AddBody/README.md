# Add Body Plugin (Java)

This plugin demonstrates HTTP body manipulation at the proxy layer by intercepting both the incoming request body and the outgoing response body. It appends a fixed suffix to the request body and fully replaces the response body with a static string. Use this plugin when you need to modify body content at the proxy layer without changing application logic — for example, enriching request payloads with metadata or normalising upstream responses. It operates during the **request body** and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `onRequestBody` callback.
2. The handler reads the existing request body as a UTF-8 string and appends `"-added-body"` to it, producing a modified body without clearing the original content.
3. The modified request is forwarded to the upstream service.
4. When the upstream responds, the proxy invokes the plugin's `onResponseBody` callback.
5. The handler discards the original response body and replaces it entirely with the static string `"body replaced"`.
6. The modified response is returned to the client.

## Implementation Notes

- **Class structure**: `AddBody` extends `ServiceCallout` and follows the Builder pattern. The inner `Builder` class extends `ServiceCallout.Builder<AddBody.Builder>`, implementing `build()` to return a new `AddBody` instance and `self()` to return the concrete builder type. This pattern allows fluent configuration chaining inherited from the base builder.
- **Request body mutation**: `onRequestBody` receives the `ProcessingResponse.Builder` and the original `HttpBody`. It calls `addBodyMutations` on `processingResponseBuilder.getRequestBodyBuilder()`, passing `body.getBody().toStringUtf8() + "-added-body"` as the new body content. The second and third arguments are `null`, indicating no `clearBody` action and no additional mutation options, so the original body is overwritten with the appended string rather than being cleared first.
- **Response body mutation**: `onResponseBody` follows the same pattern but passes the static string `"body replaced"` as the new body content, discarding the original response body entirely. Both `null` arguments again indicate no additional options.
- **`addBodyMutations` utility**: Both callbacks delegate to `ServiceCalloutTools.addBodyMutations`, a shared static helper that constructs the appropriate body mutation on the provided response builder, abstracting away the protobuf boilerplate.
- **Server startup**: The `main` method constructs an `AddBody` instance using its `Builder` with default configuration, then calls `server.start()` followed by `server.blockUntilShutdown()` to keep the process alive until manually terminated.

## Configuration

Server behaviour can be customised through the `Builder` at construction time. No configuration is required for the default setup — the body strings are hardcoded in the handlers:
- `request body suffix`: `"-added-body"` (appended to existing content)
- `response body replacement`: `"body replaced"` (replaces existing content entirely)

Optional builder parameters inherited from `ServiceCallout.Builder`:

| Builder Method | Purpose |
|---|---|
| `setIp(String)` | Overrides the server bind address |
| `setSecurePort(int)` | Sets the port for TLS-secured gRPC communication |
| `setEnablePlainTextPort(boolean)` | Enables a plaintext (insecure) gRPC port |
| `setServerThreadCount(int)` | Sets the number of threads for handling gRPC requests |

## Build

Build the plugin from the project root using Maven or Gradle:
```bash
# Maven
mvn compile

# Gradle
gradle build
```

## Run

Start the callout server with default configuration:
```bash
# Maven
mvn exec:java -Dexec.mainClass="example.AddBody"

# Gradle
gradle run --main-class="example.AddBody"

# JAR
java -cp target/your-artifact.jar example.AddBody
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=AddBodyTest

# Gradle
gradle test --tests "example.AddBodyTest"
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Request body is appended** | A request body of `"hello"` is modified to `"hello-added-body"` before being forwarded to the upstream. |
| **Empty request body is appended** | An empty request body `""` is modified to `"-added-body"` before being forwarded to the upstream. |
| **Response body is replaced** | Any response body from the upstream is replaced with `"body replaced"`. |
| **No clear action on request** | The original request bytes are overwritten with the appended string; no explicit clear is issued. |
| **No clear action on response** | The original response bytes are overwritten with the static string; no explicit clear is issued. |

## Available Languages

- [x] [Go](add_body.go)
- [x] [Java](AddBody.java)
- [x] [Python](service_callout_example.py)
