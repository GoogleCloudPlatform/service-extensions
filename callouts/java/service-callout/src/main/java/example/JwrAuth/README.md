# JWT Auth Plugin (Java)

This plugin implements JWT authentication at the proxy layer by intercepting incoming request headers, validating a Bearer token against an RSA public key loaded from the classpath, and forwarding the decoded claims as individual headers to the upstream service. Requests carrying an invalid, malformed, or missing token are denied before reaching the backend via a `denyCallout` response. Use this plugin when you need to enforce token-based authentication and propagate verified identity claims to upstream services without modifying application logic. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `onRequestHeaders` callback.
2. The handler iterates over all request headers and locates the `Authorization` header (case-insensitive match).
3. The value is split on whitespace and the `Bearer` prefix is verified; if the format is invalid or the header is absent, the token is treated as missing.
4. The extracted token is parsed and validated using `jjwt` against the RSA public key loaded from `certs/publickey.pem` at startup.
5. If validation succeeds, all decoded JWT claims are prefixed with `"decoded-"` and injected as new request headers, and the route cache is cleared to force Envoy to recompute routing.
6. If validation fails for any reason (missing token, invalid signature, expired token, or malformed JWT), `ServiceCalloutTools.denyCallout` is called and the request is rejected with an `"Authorization token is invalid"` message.

## Implementation Notes

- **Class structure**: `JwtAuth` extends `ServiceCallout` and follows the Builder pattern. The inner `Builder` extends `ServiceCallout.Builder<Builder>`, and its `build()` method propagates checked exceptions (`GeneralSecurityException`, `IOException`) from the constructor, since key loading happens at construction time. The RSA `PublicKey` is stored as a final field on the instance.
- **Public key loading**: `loadPublicKey(String pemFilePath)` reads the PEM file from the classpath using `getResourceAsStream`. It uses BouncyCastle's `PEMParser` to parse the file, extracts the `SubjectPublicKeyInfo`, encodes it as `X509EncodedKeySpec`, and constructs the `PublicKey` via `KeyFactory.getInstance("RSA")`. An `IOException` is thrown if the file is not found or if the PEM content is not a valid `SubjectPublicKeyInfo`.
- **Token extraction**: `extractJwtToken` streams over `getHeadersList()`, filters for the `Authorization` header using a case-insensitive match, reads the raw value as UTF-8 bytes, splits on whitespace, and returns the second part only if the first part is `"Bearer"` (case-insensitive). Any other format logs a warning and returns `null`.
- **Token validation**: `validateJwtToken` calls `extractJwtToken` and, if non-null, passes the token to `Jwts.parserBuilder().setSigningKey(publicKey).build().parseClaimsJws(token).getBody()`. A `SignatureException` is caught separately from the broader `JwtException` to produce distinct log messages. Both return `null`, which the caller treats as a validation failure.
- **Claims forwarding**: In `onRequestHeaders`, a successful `validateJwtToken` result is iterated with `decoded.forEach`, prefixing each claim key with `"decoded-"` and collecting into a `HashMap<String, String>`. The map's entry set is passed to `ServiceCalloutTools.addHeaderMutations` with `clearRouteCache: true` and no headers to remove or append action.
- **Request denial**: If `validateJwtToken` returns `null`, `ServiceCalloutTools.denyCallout` is called on `processingResponseBuilder.getResponseHeadersBuilder()` with the message `"Authorization token is invalid"`, causing Envoy to reject the request before it reaches the upstream.

## Configuration

The only configurable parameter is the classpath path to the RSA public key PEM file, hardcoded in the constructor:
- `default public key path`: `certs/publickey.pem` (resolved from the classpath)

All other behaviour — the header name, Bearer prefix validation, claim name prefix, route cache clearing, and denial message — is hardcoded in the handler.

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
mvn exec:java -Dexec.mainClass="example.JwtAuth"

# Gradle
gradle run --main-class="example.JwtAuth"

# JAR
java -cp target/your-artifact.jar example.JwtAuth
```

## Test

Run the unit tests for this sample:
```bash
# Maven
mvn test -Dtest=JwtAuthTest

# Gradle
gradle test --tests "example.JwtAuthTest"
```

## Expected Behavior

| Scenario | Description |
|---|---|
| **Valid token, claims forwarded** | `decoded-<claim>: <value>` headers are added for each claim in the JWT and the route cache is cleared. |
| **Missing Authorization header** | A request with no `Authorization` header is denied with `"Authorization token is invalid"`. |
| **Invalid Bearer format** | A token presented as `Authorization: Token <jwt>` or without a prefix is treated as missing and the request is denied. |
| **Invalid JWT signature** | A `SignatureException` is caught for tampered tokens and the request is denied. |
| **Expired or malformed JWT** | A `JwtException` is caught for bad tokens and the request is denied. |
| **PEM file missing at startup** | An `IOException` is thrown at construction if `certs/publickey.pem` is not on the classpath; the server fails to start. |
| **Invalid PEM content** | An `IllegalArgumentException` is thrown at construction if the PEM file is not a valid `SubjectPublicKeyInfo`; the server fails to start. |

## Available Languages

- [x] [Go](jwt_auth.go)
- [x] [Java](JwtAuth.java)
- [x] [Python](service_callout_example.py)
