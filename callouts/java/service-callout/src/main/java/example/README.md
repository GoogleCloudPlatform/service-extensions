# Java Callout Samples

This directory contains a collection of example ext_proc callout services written in Java, demonstrating various use cases, patterns, and best practices for building Envoy External Processing services. Each sample extends the `ServiceCallout` base class and uses the Builder pattern for flexible server configuration.

## Getting Started

Each sample directory contains:
- **Source code** (`*.java`)
- **README.md** with detailed documentation

## Quick Reference

### Body Manipulation

| Sample | Description |
|--------|-------------|
| [AddBody](samples/AddBody/) | Appends `"-added-body"` to the request body and replaces the response body with `"body replaced"` |

### Header Manipulation

| Sample | Description |
|--------|-------------|
| [AddHeader](samples/AddHeader/) | Adds headers to both request and response phases; removes `foo` from responses; controls route cache per phase |

### Routing & Traffic Management

| Sample | Description |
|--------|-------------|
| [Redirect](samples/Redirect/) | Returns an unconditional `301 Moved Permanently` to `http://service-extensions.com/redirect` |

### Authentication & Authorization

| Sample | Description |
|--------|-------------|
| [JwtAuth](samples/JwtAuth/) | Validates RSA-signed JWT Bearer tokens using BouncyCastle and `jjwt`; forwards decoded claims as `decoded-<claim>` headers; denies invalid requests |

### Reference Implementations

| Sample | Description |
|--------|-------------|
| [BasicCalloutServer](samples/BasicCalloutServer/) | Full four-phase reference implementation: injects headers, controls route cache, appends to request body, replaces response body |

## Builder Configuration

All samples inherit the following builder methods from `ServiceCallout.Builder`:

| Method | Purpose |
|--------|---------|
| `setIp(String)` | Overrides the server bind address |
| `setSecurePort(int)` | Sets the port for TLS-secured gRPC communication |
| `setEnablePlainTextPort(boolean)` | Enables a plaintext (insecure) gRPC port |
| `setServerThreadCount(int)` | Sets the number of threads for handling gRPC requests |

## Build

Build all samples from the project root:
```bash
# Maven
mvn compile

# Gradle
gradle build
```

## Run

Start a specific sample server:
```bash
# Maven
mvn exec:java -Dexec.mainClass="example.<SampleName>"

# Gradle
gradle run --main-class="example.<SampleName>"

# JAR
java -cp target/your-artifact.jar example.<SampleName>
```

## Test

Run all tests:
```bash
# Maven
mvn test

# Gradle
gradle test
```

Run tests for a specific sample:
```bash
# Maven
mvn test -Dtest=<SampleName>Test

# Gradle
gradle test --tests "example.<SampleName>Test"
```

## Additional Resources

- [Envoy ext_proc documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/ext_proc_filter)
- [service-extensions repository](https://github.com/GoogleCloudPlatform/service-extensions)
- [jjwt](https://github.com/jwtk/jjwt)
- [BouncyCastle](https://www.bouncycastle.org/java.html)