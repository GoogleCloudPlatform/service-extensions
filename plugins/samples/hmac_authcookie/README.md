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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_configure` | Compiles the IPv4 regex pattern at plugin initialization for efficient IP validation |
| `on_http_request_headers` | Validates the HMAC cookie by checking IP, expiration, and signature |

## Key Code Walkthrough

This plugin is only available in C++:

- **Secret key** — The plugin uses a hardcoded secret key for HMAC computation:
  ```cpp
  const std::string kSecretKey = "your_secret_key";
  ```
  **Important**: Replace this with a strong, randomly generated secret key in production. The secret must be kept confidential and should match the key used to generate the cookies.

- **IPv4 regex compilation** — In `on_configure()`, the plugin compiles a regex to validate IPv4 addresses:
  ```cpp
  ip_match.emplace("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$");
  ```
  This matches addresses like `127.0.0.1` or `192.168.1.1`.

- **Client IP extraction** — The plugin parses the `X-Forwarded-For` header:
  ```cpp
  const std::string ips = getRequestHeader("X-Forwarded-For")->toString();
  for (absl::string_view ip : absl::StrSplit(ips, ',')) {
    if (re2::RE2::FullMatch(ip, *root_->ip_match)) {
      return std::string(ip);
    }
  }
  ```
  The header may contain multiple IPs (e.g., `<existing-values>,127.0.0.1,<load-balancer-ip>`). The plugin returns the first valid IPv4 address.

- **Cookie extraction** — The plugin parses the `Cookie` header to find the `Authorization` cookie:
  ```cpp
  const std::string cookies = getRequestHeader("Cookie")->toString();
  for (absl::string_view sp : absl::StrSplit(cookies, "; ")) {
    const std::pair<std::string, std::string> cookie =
        absl::StrSplit(sp, absl::MaxSplits('=', 1));
    if (cookie.first == "Authorization") {
      return cookie.second;
    }
  }
  ```
  The `Cookie` header contains multiple cookies separated by `; `. The plugin splits on `=` with a max of 1 split to handle cookie values that contain `=`.

- **Cookie parsing** — The plugin parses the `Authorization` cookie format:
  ```cpp
  std::pair<std::string_view, std::string_view> payload_and_hash =
      absl::StrSplit(cookie, ".");
  std::string payload;
  std::string hash;
  if (absl::Base64Unescape(payload_and_hash.first, &payload) &&
      absl::Base64Unescape(payload_and_hash.second, &hash)) {
    return std::pair{payload, hash};
  }
  ```
  Both the payload and hash are base64-decoded.

- **HMAC computation** — The plugin computes HMAC-SHA256 using OpenSSL:
  ```cpp
  std::string computeHmacSignature(std::string_view data) {
    unsigned char result[EVP_MAX_MD_SIZE];
    unsigned int len;
    HMAC(EVP_sha256(), kSecretKey.c_str(), kSecretKey.length(),
         reinterpret_cast<const unsigned char*>(std::string{data}.c_str()),
         data.length(), result, &len);
    return absl::BytesToHexString(std::string(result, result + len));
  }
  ```
  The result is converted to a hex string for comparison.

- **Expiration validation** — The plugin compares the current time (in nanoseconds) to the expiration timestamp:
  ```cpp
  const int64_t unix_now = absl::ToUnixNanos(absl::Now());
  int64_t parsed_expiration_timestamp;
  return absl::SimpleAtoi(expiration_timestamp, &parsed_expiration_timestamp) &&
         unix_now <= parsed_expiration_timestamp;
  ```

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

| Scenario | Input | Output |
|---|---|---|
| **NoXForwardedForHeader** | No `X-Forwarded-For` header; `Authorization` cookie present | 403 with `"Access forbidden - missing client IP.\n"` (IP extraction failed) |
| **NoClientIP** | `X-Forwarded-For: <existing-values>,<not-an-ip>,<not-an-ip-also>` (no valid IP); `Authorization` cookie present | 403 with `"Access forbidden - missing client IP.\n"` (no valid IPv4 found) |
| **WithValidHMACHash** | `X-Forwarded-For: <existing-values>,127.0.0.1,<load-balancer-ip>`; Valid `Authorization` cookie for IP `127.0.0.1` expiring Jan 01 2025 | Request allowed (all validations pass) |
| **WithExpiredHMACHash** | `X-Forwarded-For: <existing-values>,127.0.0.1,<load-balancer-ip>`; `Authorization` cookie for IP `127.0.0.1` expired Dec 30 2024 | 403 with `"Access forbidden - hash expired.\n"` (cookie expired) |
| **WithInvalidClientIp** | `X-Forwarded-For: <existing-values>,127.0.0.2,<load-balancer-ip>`; `Authorization` cookie for IP `127.0.0.1` | 403 with `"Access forbidden - invalid client IP.\n"` (IP mismatch) |
| **WithInvalidHMACHash** | `X-Forwarded-For: <existing-values>,127.0.0.1,<load-balancer-ip>`; `Authorization` cookie with invalid HMAC signature | 403 with `"Access forbidden - invalid HMAC hash.\n"` (signature verification failed) |
| **NoCookie** | `X-Forwarded-For: <existing-values>,127.0.0.1,<load-balancer-ip>`; No `Authorization` cookie | 403 with `"Access forbidden - missing HMAC cookie.\n"` (cookie missing) |
| **InvalidCookie** | `X-Forwarded-For: <existing-values>,127.0.0.1,<load-balancer-ip>`; `Authorization` cookie with invalid format | 403 with `"Access forbidden - invalid HMAC cookie.\n"` (parsing failed) |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
