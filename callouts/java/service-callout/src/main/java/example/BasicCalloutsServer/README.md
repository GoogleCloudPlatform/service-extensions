# Basic Callout Server Plugin (Java)

This plugin demonstrates a complete ext_proc callout service by handling all four HTTP processing phases simultaneously: request headers, response headers, request body, and response body. It injects custom headers into both the request and response, appends a suffix to the request body, and fully replaces the response body with a static string. Use this plugin as a reference implementation or starting point when you need a full-featured callout service that intercepts every phase of the HTTP lifecycle. It operates during the **request headers**, **response headers**, **request body**, and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `onRequestHeaders` callback.
2. The handler adds `request-header: added-request` and `c: d` to the incoming request headers, and sets `clearRouteCache` to `true` to force Envoy to recompute its routing decision.
3. The proxy then invokes `onRequestBody`, which reads the existing request body and appends `"-added-body"` to it.
4. The modified request is forwarded to the upstream service.
5. When the upstream responds, the proxy invokes `onResponseHeaders`, which adds `response-header: added-response` and `c: d` to the response headers, removes the `foo` header, and preserves the route cache.
6. The proxy then invokes `onResponseBody`, which discards the original response body and replaces it entirely with `"body replaced"`.
7. The fully modified response is returned to the client.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `onRequestHeaders` | Adds `request-header: added-request` and `c: d` to request headers; clears the route cache |
| `onResponseHeaders` | Adds `response-header: added-response` and `c: d` to response headers; removes `foo`; preserves route cache |
| `onRequestBody` | Reads the existing request body and appends `"-added-body"` to it |
| `onResponseBody` | Replaces the outgoing response body entirely with `"body replaced"` |

## Key Code Walkthrough

- **Class structure** — `BasicCalloutServer` extends `ServiceCallout` and follows the Builder pattern. The inner `Builder` class extends `ServiceCallout.Builder<BasicCalloutServer.Builder>`, implementing `build()` to return a new `BasicCalloutServer` instance and `self()` to return the concrete builder type for fluent chaining. This is the most complete example of the standard Java callout service pattern.

- **Request header mutation** — `onRequestHeaders` calls `addHeaderMutations` on `processingResponseBuilder.getRequestHeadersBuilder()`, passing an `ImmutableMap` of two entries as headers to add, `null` for headers to remove, `true` for `clearRouteCache`, and `null` for the append action. Setting `clearRouteCache` to `true` tells Envoy to discard any previously computed route and re-evaluate routing based on the mutated headers.

- **Response header mutation** — `onResponseHeaders` calls `addHeaderMutations` on `processingResponseBuilder.getResponseHeadersBuilder()`, passing a different `ImmutableMap` of two entries as headers to add, an `ImmutableList.of("foo")` as the header to remove, `false` for `clearRouteCache`, and `null` for the append action. Route cache is preserved because response-phase routing decisions are already finalised.

- **Request body mutation** — `onRequestBody` calls `addBodyMutations` on `processingResponseBuilder.getRequestBodyBuilder()`, passing `body.getBody().toStringUtf8() + "-added-body"` as the new body content. Both remaining arguments are `null`, indicating no clear action and no additional options — the original content is overwritten with the appended string.

- **Response body mutation** — `onResponseBody` calls `addBodyMutations` on `processingResponseBuilder.getResponseBodyBuilder()`, passing the static string `"body replaced"` as the new body content, discarding the original response body entirely.

- **Mutation utilities** — All four callbacks delegate to static helpers from `ServiceCalloutTools`: `addHeaderMutations` for header phase callbacks and `addBodyMutations` for body phase callbacks, both abstracting away the protobuf mutation boilerplate.

- **Server startup** — The `main` method constructs a `BasicCalloutServer` instance using its `Builder` with default configuration, then calls `server.start()` followed by `server.blockUntilShutdown()` to keep the process alive until manually terminated.

## Configuration

No configuration is required for the default setup. All injected values are hardcoded directly in each callback:

- Request headers added: `request-header: added-request`, `c: d`
- Response headers added: `response-header: added-response`, `c: d`
- Response headers removed: `foo`
- Request body: original content with `"-added-body"` appended
- Response body replacement: `"body replaced"`
- Request phase route cache: cleared (`true`)
- Response phase route cache: preserved (`false`)

Optional builder parameters inherited from `ServiceCallout.Builder`:

| Builder Method | Purpose |
|---|---|
| `setIp(String)` | Overrides the server bind address |
| `setSecurePort(int)` | Sets the port for TLS-secured gRPC communication |
| `setEnablePlainTextPort(boolean)` | Enables a plaintext (insecure) gRPC port |
| `setServerThreadCount(int)` | Sets the number of threads for handling gRPC requests |

## Build

Build the plugin from the project root using Maven or Gradle (adjust for your build tool):
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
mvn exec:java -Dexec.mainClass="example.BasicCalloutServer"

# Gradle
gradle run --main-class="example.BasicCalloutServer"

# JAR
java -cp target/your-artifact.jar example.BasicCalloutServer
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=BasicCalloutServerTest

# Gradle
gradle test --tests "example.BasicCalloutServerTest"
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request headers added** | Any HTTP request | `request-header: added-request` and `c: d` injected into request headers |
| **Request route cache cleared** | Any HTTP request | Envoy recomputes routing after request header mutation |
| **Response headers added** | Any HTTP response | `response-header: added-response` and `c: d` injected into response headers |
| **Response header removed** | Response containing `foo` header | `foo` header stripped from response |
| **Response route cache preserved** | Any HTTP response | Envoy routing decision unchanged after response header mutation |
| **Request body appended** | Request body `"hello"` | Modified body `"hello-added-body"` forwarded to upstream |
| **Empty request body appended** | Request body `""` | Modified body `"-added-body"` forwarded to upstream |
| **Response body replaced** | Any response body from upstream | Response body replaced with `"body replaced"` |
| **No append action** | Any request or response headers | Headers set (overwrite existing values) rather than appended |

## Available Languages

- [x] [Java](BasicCalloutServer.java)
- [x] [Go](basic_callout_server.go)
