# HMAC Auth Cookie Plugin

This plugin implements secure cookie-based authentication using HMAC (Hash-based Message Authentication Code) signatures. It validates authentication cookies that bind a client's IP address and an expiration timestamp to prevent cookie theft, replay attacks, and unauthorized access. The plugin verifies that the cookie's HMAC signature is valid, the client IP matches the IP in the cookie, and the cookie has not expired. Use this plugin when you need to implement stateless session authentication, prevent session hijacking, or add an additional security layer to cookie-based authentication. It operates during the **request headers** processing phase.

## How It Works

1. **Client IP extraction**: When the proxy receives an HTTP request, the plugin invokes `on_http_request_headers`:
   - The plugin reads the `X-Forwarded-For` header and extracts the first valid IPv4 address (format: `xxx.xxx.xxx.xxx`).
   - If no valid IP is found, the request is rejected with a 403 Forbidden response.

2. **Cookie extraction**: The plugin reads the `Cookie` header and searches for an `Authorization` cookie.
   - If the cookie is missing, the request is rejected with a 403 Forbidden response.

3. **Cookie parsing**: The plugin parses the `Authorization` cookie, which has the format:
   ```
   Base64(payload) + "." + Base64(HMAC-SHA256(payload))
   ```
   - The payload format is: `client_ip,expiration_timestamp_nanos`
   - Both parts are base64-encoded.
   - If parsing fails, the request is rejected with a 403 Forbidden response.

4. **HMAC signature verification**: The plugin computes the HMAC-SHA256 hash of the payload using a secret key and compares it to the hash in the cookie.
   - If the hashes don't match, the request is rejected with a 403 Forbidden response (indicating the cookie was tampered with or generated with a different secret).

5. **IP address validation**: The plugin extracts the client IP from the payload and compares it to the IP from the `X-Forwarded-For` header.
   - If they don't match, the request is rejected with a 403 Forbidden response (preventing cookie theft).

6. **Expiration validation**: The plugin checks if the current time (in nanoseconds since Unix epoch) is earlier than the expiration timestamp in the payload.
   - If the cookie has expired, the request is rejected with a 403 Forbidden response.

7. **Success**: If all validations pass, the plugin allows the request to proceed to the upstream server.

## Implementation Notes

- **Regex compilation**: Compiles a regex matching IPv4 strings at initialization.
- **Header parsing**: Extracts the client IP from the `X-Forwarded-For` header and an `Authorization` payload from the `Cookie` header.
- **HMAC validation**: Computes an HMAC-SHA256 hash using OpenSSL on the extracted payload and compares it against the signed hash in the cookie.
- **Security checks**: Validates both the IP claim in the payload against the request origin, and the expiration claim against the current Unix time.

## Configuration

No configuration required. The secret key is hardcoded in the plugin source.

**Important**: Replace `kSecretKey = "your_secret_key"` with a strong, randomly generated secret in production. The secret must be at least 32 bytes long for security.

## Cookie Format

The `Authorization` cookie has the following format:

```
Base64(payload) + "." + Base64(HMAC-SHA256(payload))
```

**Payload format**: `client_ip,expiration_timestamp_nanos`

**Example**:
- Client IP: `127.0.0.1`
- Expiration: `1735700400000000000` (Wed Jan 01 2025 03:00:00 GMT+0000)
- Payload: `127.0.0.1,1735700400000000000`
- Base64(payload): `MTI3LjAuMC4xLDE3MzU3MDA0MDAwMDAwMDAwMDA`
- HMAC-SHA256(payload): `18f79bc0a307c8b2b891b14473a2aa69caed4ef360ccb54ce57af4173dc00fd4`
- Base64(HMAC): `MThmNzliYzBhMzA3YzhiMmI4OTFiMTQ0NzNhMmFhNjljYWVkNGVmMzYwY2NiNTRjZTU3YWY0MTczZGMwMGZkNA`
- Final cookie: `MTI3LjAuMC4xLDE3MzU3MDA0MDAwMDAwMDAwMDA.MThmNzliYzBhMzA3YzhiMmI4OTFiMTQ0NzNhMmFhNjljYWVkNGVmMzYwY2NiNTRjZTU3YWY0MTczZGMwMGZkNA`

## Build

Build the plugin for C++ from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/hmac_authcookie:plugin_cpp.wasm
```

**Note**: Only C++ implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/hmac_authcookie/tests.textpb \
    --plugin /mnt/bazel-bin/samples/hmac_authcookie/plugin_cpp.wasm

# Using Bazel
bazelisk test --test_output=all //samples/hmac_authcookie:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb) (test environment time: Tue Dec 31 2024 03:00:00 GMT+0000):

| Scenario | Description |
|---|---|
| **NoXForwardedForHeader** | Rejects the request when the origin IP header is completely missing. |
| **NoClientIP** | Rejects the request when no valid IPv4 address can be parsed from the origin header. |
| **WithValidHMACHash** | Allows the request when the token signature, IP claim, and timestamp claim are all valid. |
| **WithExpiredHMACHash** | Rejects the request when the cookie expiration time is in the past. |
| **WithInvalidClientIp** | Rejects the request when the IP from the cookie payload does not match the actual client IP. |
| **WithInvalidHMACHash** | Rejects the request when the cryptographic signature of the token is incorrect. |
| **NoCookie** | Rejects the request when the expected cookie header is missing. |
| **InvalidCookie** | Rejects the request when the cookie format cannot be successfully parsed. |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
