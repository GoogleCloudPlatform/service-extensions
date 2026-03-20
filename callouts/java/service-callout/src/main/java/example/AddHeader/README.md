# Add Header Plugin (Java)

This plugin demonstrates HTTP header manipulation at the proxy layer by intercepting both incoming request headers and outgoing response headers. It adds new headers to each phase, removes a specific header from the response, and controls route cache invalidation independently per phase. Use this plugin when you need to inject metadata headers into requests, enrich or sanitise response headers, or force Envoy to recompute its routing decision after a header mutation. It operates during the **request headers** and **response headers** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `onRequestHeaders` callback.
2. The handler adds two headers to the request — `request-header: added-request` and `c: d` — and sets `clearRouteCache` to `true`, instructing Envoy to recompute the routing decision after the mutation.
3. The modified request is forwarded to the upstream service.
4. When the upstream responds, the proxy invokes the plugin's `onResponseHeaders` callback.
5. The handler adds two headers to the response — `response-header: added-response` and `c: d` — and simultaneously removes the `foo` header. The route cache is left intact (`clearRouteCache: false`).
6. The modified response is returned to the client.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `onRequestHeaders` | Adds `request-header: added-request` and `c: d` to request headers; clears the route cache |
| `onResponseHeaders` | Adds `response-header: added-response` and `c: d` to response headers; removes `foo`; preserves route cache |

## Key Code Walkthrough

- **Class structure** — `AddHeader` extends `ServiceCallout` and follows the Builder pattern. The inner `Builder` class extends `ServiceCallout.Builder<AddHeader.Builder>`, implementing `build()` to return a new `AddHeader` instance and `self()` to return the concrete builder type for fluent chaining.

- **Request header mutation** — `onRequestHeaders` calls `addHeaderMutations` on `processingResponseBuilder.getRequestHeadersBuilder()`, passing an `ImmutableMap` of two entries as the headers to add, `null` for headers to remove, `true` for `clearRouteCache`, and `null` for the append action. Setting `clearRouteCache` to `true` tells Envoy to discard any previously computed route and re-evaluate routing based on the mutated headers.

- **Response header mutation** — `onResponseHeaders` calls `addHeaderMutations` on `processingResponseBuilder.getResponseHeadersBuilder()`, passing a different `ImmutableMap` of two entries as headers to add, an `ImmutableList.of("foo")` as the single header to remove, `false` for `clearRouteCache`, and `null` for the append action. Route cache is preserved because response-phase routing decisions are already finalised.

- **`addHeaderMutations` utility** — Both callbacks delegate to `ServiceCalloutTools.addHeaderMutations`, a shared static helper that applies the provided add, remove, cache, and append instructions to the given response builder, abstracting away the protobuf mutation boilerplate.

- **Server startup** — The `main` method constructs an `AddHeader` instance using its `Builder` with default configuration, then calls `server.start()` followed by `server.blockUntilShutdown()` to keep the process alive until manually terminated.

## Configuration

No configuration is required for the default setup. All header names, values, and cache settings are hardcoded in the handlers:

- Request headers added: `request-header: added-request`, `c: d`
- Response headers added: `response-header: added-response`, `c: d`
- Response headers removed: `foo`
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
mvn exec:java -Dexec.mainClass="example.AddHeader"

# Gradle
gradle run --main-class="example.AddHeader"

# JAR
java -cp target/your-artifact.jar example.AddHeader
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=AddHeaderTest

# Gradle
gradle test --tests "example.AddHeaderTest"
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request headers added** | Any HTTP request | `request-header: added-request` and `c: d` injected into request headers |
| **Request route cache cleared** | Any HTTP request | Envoy recomputes routing after request header mutation |
| **Response headers added** | Any HTTP response | `response-header: added-response` and `c: d` injected into response headers |
| **Response header removed** | Response containing `foo` header | `foo` header stripped from response |
| **Response route cache preserved** | Any HTTP response | Envoy routing decision unchanged after response header mutation |
| **No append action** | Any request or response | Headers set (overwrite existing values) rather than appended |

## Available Languages

- [x] [Go](add_header.go)
- [x] [Java](AddHeader.java)
- [x] [Python](service_callout_example.py)