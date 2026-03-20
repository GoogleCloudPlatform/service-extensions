# Redirect Plugin (Java)

This plugin implements an unconditional HTTP redirect at the proxy layer by intercepting every incoming request and immediately returning a `301 Moved Permanently` response with a hardcoded `Location` header, before the request ever reaches the upstream service. Use this plugin when you need to enforce a blanket redirect for all traffic through a proxy — such as domain migrations, protocol enforcement, or legacy endpoint retirement — without involving any backend logic. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `onRequestHeaders` callback.
2. The handler unconditionally constructs an `HttpStatus` with status code `301` (Moved Permanently).
3. A `Location: http://service-extensions.com/redirect` header is prepared as an `ImmutableMap` entry.
4. `ServiceCalloutTools.buildImmediateResponse` is called on `processingResponseBuilder.getImmediateResponseBuilder()`, attaching the status, the redirect header, no headers to remove, and no response body.
5. The `ProcessingResponse` is returned as an immediate response, instructing Envoy to short-circuit the request and send the redirect directly to the client.
6. The upstream service is never contacted.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `onRequestHeaders` | Intercepts every incoming HTTP request and returns an immediate `301` redirect response with a `Location` header |

## Key Code Walkthrough

- **Class structure** — `Redirect` extends `ServiceCallout` and follows the Builder pattern. The inner `Builder` extends `ServiceCallout.Builder<Redirect.Builder>`, implementing `build()` to return a new `Redirect` instance and `self()` to return the concrete builder type for fluent chaining. Only the request headers phase is handled, since the request is terminated before any other phase is reached.

- **Status construction** — `HttpStatus` is built using `HttpStatus.newBuilder().setCode(StatusCode.forNumber(301)).build()`, wrapping the numeric status code `301` in the Envoy protobuf `HttpStatus` message expected by the `ImmediateResponse` builder.

- **Redirect header** — The `Location` header is defined as an `ImmutableMap.of("Location", "http://service-extensions.com/redirect")` and passed directly to `buildImmediateResponse` as the headers-to-add map.

- **Immediate response construction** — `ServiceCalloutTools.buildImmediateResponse` is called on `processingResponseBuilder.getImmediateResponseBuilder()` rather than on a headers or body builder. This populates the `ImmediateResponse` field of the `ProcessingResponse`, signalling Envoy to bypass the upstream entirely and reply to the client directly with the constructed status and headers.

- **Unconditional behaviour** — Unlike routing or filtering plugins, this handler performs no inspection of the incoming request. Every request — regardless of path, method, or headers — receives the same redirect response.

- **Server startup** — The `main` method constructs a `Redirect` instance using its `Builder` with default configuration, then calls `server.start()` followed by `server.blockUntilShutdown()` to keep the process alive until manually terminated.

## Configuration

No configuration is required for the default setup. The redirect target and status code are hardcoded directly in the handler:

- HTTP status code: `301` (Moved Permanently)
- Redirect target: `http://service-extensions.com/redirect`
- Headers to remove: none
- Response body: none

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
mvn exec:java -Dexec.mainClass="example.Redirect"

# Gradle
gradle run --main-class="example.Redirect"

# JAR
java -cp target/your-artifact.jar example.Redirect
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=RedirectTest

# Gradle
gradle test --tests "example.RedirectTest"
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Any request is redirected** | Any HTTP request regardless of path or method | `301 Moved Permanently` with `Location: http://service-extensions.com/redirect` |
| **Upstream is never reached** | Any HTTP request | Request short-circuited at the proxy; no upstream connection made |
| **No body in response** | Any HTTP request | Immediate response returned with no body content |
| **No headers removed** | Any HTTP request | No existing headers stripped from the response |

## Available Languages

- [x] [Go](redirect.go)
- [x] [Java](Redirect.java)
- [x] [Python](service_callout_example.py)
