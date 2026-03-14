# JWT Auth Plugin

This plugin implements JWT (JSON Web Token) authentication by validating tokens passed as query parameters in request URLs. It verifies JWT signatures using RSA public key cryptography, validates token structure, and removes the token from the URL before forwarding the request to the upstream server. Use this plugin when you need to implement stateless API authentication, protect endpoints with cryptographically signed tokens, or enable secure URL-based token validation without cookies or headers. It operates during the **request headers** processing phase.

## How It Works

1. **Plugin initialization**: When the plugin starts, the proxy invokes `on_configure` (C++) or `OnPluginStart` (Go):
   - The plugin reads the configuration file containing an RSA public key in PEM format.
   - **C++** uses the `jwt_verify_lib` to parse the PEM key and create a `Jwks` object.
   - **Go** uses `crypto/x509` to parse the PEM key and extract the RSA public key.
   - If key parsing fails, the plugin initialization fails.

2. **Request processing**: When the proxy receives an HTTP request, it invokes `on_http_request_headers`:
   - The plugin reads the `:path` pseudo-header and parses it as a URL.

3. **Token extraction**: The plugin searches for a `jwt` query parameter:
   - If missing, the request is rejected with a 403 Forbidden response.

4. **Token structure validation**: The plugin parses the JWT to verify it has valid structure (header.payload.signature):
   - **C++** uses `jwt.parseFromString()` from `jwt_verify_lib`.
   - **Go** uses `jwt.NewParser().ParseUnverified()` from `github.com/golang-jwt/jwt/v5`.
   - If parsing fails, the request is rejected with a 403 Forbidden response.

5. **Signature verification**: The plugin verifies the JWT signature using the RSA public key:
   - **C++** uses `google::jwt_verify::verifyJwt()` to validate the signature and claims.
   - **Go** uses `jwt.Parse()` with a key function that returns the RSA public key and validates the signing method.
   - If verification fails (invalid signature, expired token, or other validation errors), the request is rejected with a 403 Forbidden response.

6. **Token removal**: If the token is valid, the plugin removes the `jwt` query parameter from the URL and updates the `:path` header.

7. **Success**: If all validations pass, the plugin allows the request to proceed to the upstream server with the cleaned URL.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_configure` (C++) / `OnPluginStart` (Go) | Loads and parses the RSA public key from the configuration file |
| `on_http_request_headers` | Extracts JWT from URL, validates signature, and removes token from path |

## Key Code Walkthrough

The core logic is conceptually identical between C++ and Go implementations:

- **RSA public key loading** — The plugin loads the public key during initialization:
  - **C++**:
    ```cpp
    const std::string rsa_key = config_->toString();
    jwks_ = google::jwt_verify::Jwks::createFrom(
        rsa_key, google::jwt_verify::Jwks::Type::PEM);
    ```
    The `jwt_verify_lib` library handles PEM decoding and key parsing.

  - **Go**:
    ```go
    block, _ := pem.Decode(config)
    pub, err := x509.ParsePKIXPublicKey(block.Bytes)
    if err != nil {
        pub, err = x509.ParsePKCS1PublicKey(block.Bytes)
    }
    rsaPub, ok := pub.(*rsa.PublicKey)
    ```
    Go tries both PKIX (standard) and PKCS1 (legacy) formats to support different PEM encodings.

- **URL parsing and token extraction** — The plugin parses the `:path` header:
  - **C++**:
    ```cpp
    boost::system::result<boost::urls::url> url =
        boost::urls::parse_uri_reference(path->view());
    auto it = url->params().find("jwt");
    ```
  - **Go**:
    ```go
    u, err := url.ParseRequestURI(path)
    query := u.Query()
    jwtToken := query.Get("jwt")
    ```

- **JWT parsing** — The plugin validates token structure:
  - **C++**:
    ```cpp
    google::jwt_verify::Jwt jwt;
    if (jwt.parseFromString((*it).value) != google::jwt_verify::Status::Ok) {
        sendLocalResponse(403, "", "Access forbidden - invalid token.\n", {});
    }
    ```
  - **Go**:
    ```go
    parser := jwt.NewParser(jwt.WithoutClaimsValidation())
    _, _, err = parser.ParseUnverified(jwtToken, jwt.MapClaims{})
    if err != nil {
        ctx.sendResponse(403, "Access forbidden - invalid token.\n")
    }
    ```

- **Signature verification** — The plugin verifies the JWT signature:
  - **C++**:
    ```cpp
    const auto status = google::jwt_verify::verifyJwt(jwt, *root_->jwks());
    if (status != google::jwt_verify::Status::Ok) {
        sendLocalResponse(403, "", "Access forbidden.\n", {});
    }
    ```
    The `verifyJwt` function checks the signature and validates standard claims (exp, nbf, etc.).

  - **Go**:
    ```go
    token, err := jwt.Parse(jwtToken, func(token *jwt.Token) (interface{}, error) {
        if _, ok := token.Method.(*jwt.SigningMethodRSA); !ok {
            return nil, fmt.Errorf("unexpected signing method")
        }
        return ctx.publicKey, nil
    })
    if err != nil || !token.Valid {
        ctx.sendResponse(403, "Access forbidden.\n")
    }
    ```
    The key function validates that the token uses RSA signing and returns the public key for verification.

- **Token removal** — After validation, the plugin removes the `jwt` parameter:
  - **C++**:
    ```cpp
    url->params().erase(it);
    replaceRequestHeader(":path", url->buffer());
    ```
  - **Go**:
    ```go
    query.Del("jwt")
    u.RawQuery = query.Encode()
    proxywasm.ReplaceHttpRequestHeader(":path", u.String())
    ```

## Configuration

The plugin requires an RSA public key in PEM format. The key must be provided as a configuration file.

**Example public key** (`publickey.pem`):
```
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1SU1LfVLPHCozMxH2Mo
4lgOEePzNm0tRgeLezV6ffAt0gunVTLw7onLRnrq0/IzW7yWR7QkrmBL7jTKEn5u
+qKhbwKfBstIs+bMY2Zkp18gnTxKLxoS2tFczGkPLPgizskuemMghRniWaoLcyeh
kd3qqGElvW/VDL5AaWTg0nLVkjRo9z+40RQzuVaE8AkAFmxZzow3x+VJYKdjykkJ
0iT9wCS0DRTXu269V264Vf/3jvredZiKRkgwlL9xNAwxXFg0x/XFw005UWVRIkdg
cKWTjpBP2dPwVZ4WWC+9aGVd+Gyn1o0CLelf4rEjGoXbAAEgAqeGUxrcIlbjXfbc
mwIDAQAB
-----END PUBLIC KEY-----
```

**Note**: Replace this example key with your actual RSA public key. The corresponding private key is used to sign JWTs (typically by your authentication service).

## JWT Format

The `jwt` query parameter should contain a standard JWT in the format:
```
header.payload.signature
```

Each part is base64url-encoded JSON.

**Example JWT**:
```
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.NHVaYe26MbtOYhSKkoKYdFVomg4i8ZJd8_-RU8VNbftc4TSMb4bXP3l3YlNWACwyXPGffz5aXHc6lty1Y2t4SWRqGteragsVdZufDn5BlnJl9pdR_kdVFUsra2rWKEofkZeIC4yWytE58sMIihvo9H1ScmmVwBcQP6XETqYd0aSHp1gOa9RdUPDvoXQ5oqygTqVtxaDr6wUFKrKItgBMzWIdNZ6y7O9E0DhEPTbE9rfBo6KTFsHAZnMg4k68CDp2woYIaXbmYTWcvbzIuHO7_37GT79XdIwkm95QJ7hYC9RiwrV7mesbY4PAahERJawntho0my942XheVLmGwLMBkQ
```

**Decoded header**:
```json
{
  "alg": "RS256",
  "typ": "JWT"
}
```

**Decoded payload**:
```json
{
  "sub": "1234567890",
  "name": "John Doe",
  "admin": true,
  "iat": 1516239022
}
```

The signature is computed using the RSA-SHA256 algorithm with the private key.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/jwt_auth:plugin_cpp.wasm

# Go
bazelisk build //samples/jwt_auth:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/jwt_auth/tests.textpb \
    --plugin /mnt/bazel-bin/samples/jwt_auth/plugin_cpp.wasm \
    --config /mnt/samples/jwt_auth/publickey.pem

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/jwt_auth:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **WithValidJwt** | `:path: /admin?jwt=<valid_token>&param=value` | `:path: /admin?param=value` (valid JWT removed, request allowed) |
| **NoJwt** | `:path: /admin` (no jwt parameter) | 403 with `"Access forbidden - missing token.\n"` |
| **InvalidJwt** | `:path: /admin?jwt=ddssdsds.ddfdffd.dsssd` (malformed JWT) | 403 with `"Access forbidden - invalid token.\n"` (parsing failed) |
| **NotAllowedJwt** | `:path: /admin?jwt=<token_with_invalid_signature>` | 403 with `"Access forbidden.\n"` (signature verification failed) |

## Available Languages

- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)
- [ ] Rust (not available)
