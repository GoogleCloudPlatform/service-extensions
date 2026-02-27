# HMAC Token Validation Plugin

This plugin implements request authentication using HMAC (Hash-based Message Authentication Code) tokens sent in the `Authorization` header. It validates that requests include a properly signed, non-expired token computed from the HTTP method, path, and timestamp. Use this plugin when you need to implement stateless API authentication, protect endpoints from unauthorized access, or validate time-limited tokens without requiring a database. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. **Authorization header check**: The plugin reads the `Authorization` header:
   - If missing or empty, the request is rejected with a 401 Unauthorized response.

3. **Scheme validation**: The plugin verifies that the header starts with `"HMAC "` (case-insensitive):
   - If not, the request is rejected with a 400 Bad Request response.

4. **Token parsing**: The plugin parses the token in the format `timestamp:hmac_signature`:
   - `timestamp`: Unix timestamp (seconds) when the token was created
   - `hmac_signature`: HMAC-MD5 hash of `METHOD:PATH:timestamp`
   - If the format is invalid, the request is rejected with a 400 Bad Request response.

5. **Timestamp validation**: The plugin parses the timestamp as an integer:
   - If parsing fails, the request is rejected with a 400 Bad Request response.

6. **Expiration check**: The plugin compares the current time to the token timestamp:
   - If the difference exceeds 300 seconds (5 minutes), the request is rejected with a 403 Forbidden response.

7. **Required headers check**: The plugin verifies that `:path` and `:method` headers are present:
   - If missing, the request is rejected with a 400 Bad Request response.

8. **HMAC computation**: The plugin constructs the message string `METHOD:PATH:timestamp` and computes the expected HMAC-MD5 signature using the secret key:
   - If HMAC computation fails, the request is rejected with a 500 Internal Server Error response.

9. **Signature verification**: The plugin compares the computed HMAC with the token's HMAC:
   - If they don't match, the request is rejected with a 403 Forbidden response.

10. **Success**: If all validations pass, the plugin allows the request to proceed to the upstream server.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_configure` | Plugin initialization (currently no-op but can be used for config loading) |
| `on_http_request_headers` | Validates the HMAC token in the `Authorization` header |

## Key Code Walkthrough

This plugin is only available in C++:

- **Secret key and token validity** — Configured in the root context:
  ```cpp
  std::string secret_key_ = "your-secret-key";
  const int64_t token_validity_seconds_ = 300;  // 5 minutes
  ```
  **Important**: Replace `secret_key_` with a strong, randomly generated secret in production. The token validity period can be adjusted based on security requirements.

- **Authorization header validation** — The plugin checks for the header and scheme:
  ```cpp
  auto auth_header = getRequestHeader("authorization");
  if (!auth_header || auth_header->view().empty()) {
      sendLocalResponse(401, 
                       "WWW-Authenticate: HMAC realm=\"api\"",
                       "Missing Authorization header", 
                       {});
      return FilterHeadersStatus::StopIteration;
  }
  
  if (!absl::StartsWithIgnoreCase(auth_value, "HMAC ")) {
      sendLocalResponse(400, "", "Invalid Authorization scheme. Use 'HMAC'", {});
      return FilterHeadersStatus::StopIteration;
  }
  ```
  The scheme check is case-insensitive, so `"HMAC"`, `"hmac"`, or `"Hmac"` are all accepted.

- **Token parsing** — The plugin splits the token on the `:` character:
  ```cpp
  std::string token = std::string(auth_value.substr(prefix.size()));
  std::vector<std::string> token_parts(absl::StrSplit(token, absl::MaxSplits(':', 1)));
  
  if (token_parts.size() != 2) {
      sendLocalResponse(400, "", "Invalid token format: expected 'timestamp:hmac'", {});
      return FilterHeadersStatus::StopIteration;
  }
  ```
  The `MaxSplits(':', 1)` ensures the string is split into exactly 2 parts, allowing the HMAC signature to contain `:` characters.

- **Expiration check** — The plugin validates the token age:
  ```cpp
  const uint64_t current_time = static_cast<uint64_t>(absl::ToUnixSeconds(absl::Now()));
  if ((current_time - token_timestamp) > root_->token_validity_seconds_) {
      sendLocalResponse(403, "", "Token expired", {});
      return FilterHeadersStatus::StopIteration;
  }
  ```

- **HMAC computation** — The plugin computes HMAC-MD5 using OpenSSL:
  ```cpp
  std::string computeHmacMd5(const std::string& message, const std::string& key) {
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;
    
    unsigned char* hmac_result = HMAC(EVP_md5(), 
                                     key.data(), key.size(),
                                     reinterpret_cast<const unsigned char*>(message.data()), message.size(),
                                     hash, &hash_len);
    
    if (hmac_result == nullptr || hash_len == 0) {
      return "";
    }
    
    return absl::BytesToHexString(absl::string_view(reinterpret_cast<const char*>(hash), hash_len));
  }
  ```
  The message format is `METHOD:PATH:timestamp` (e.g., `GET:/api:1717000000`). The result is converted to a lowercase hex string.

- **Signature comparison** — The plugin performs a constant-time string comparison:
  ```cpp
  if (expected_hmac != token_hmac) {
      sendLocalResponse(403, "", "Invalid HMAC", {});
      return FilterHeadersStatus::StopIteration;
  }
  ```

## Configuration

No external configuration file required. The secret key and token validity period are hardcoded in the root context.

**Configurable values**:
- **`secret_key_`**: `"your-secret-key"` — **Replace with a strong secret in production** (minimum 32 bytes)
- **`token_validity_seconds_`**: `300` (5 minutes) — Adjust based on security/usability requirements

## Token Format

The `Authorization` header must use the following format:

```
Authorization: HMAC timestamp:hmac_signature
```

**Components**:
- **`HMAC`**: Scheme identifier (case-insensitive)
- **`timestamp`**: Unix timestamp in seconds when the token was created
- **`hmac_signature`**: HMAC-MD5 hex string of `METHOD:PATH:timestamp`

**Message format**: `METHOD:PATH:timestamp`

**Example**:
```
Method: GET
Path: /api/users
Timestamp: 1717000000
Secret: your-secret-key

Message: GET:/api/users:1717000000
HMAC-MD5(message, secret): a1b2c3d4e5f6... (32 hex chars)

Authorization header:
Authorization: HMAC 1717000000:a1b2c3d4e5f6...
```

## Token Generation Example

**Python**:
```python
import hmac
import hashlib
import time

def generate_hmac_token(method, path, secret_key):
    """Generate HMAC token for request authentication."""
    timestamp = int(time.time())
    message = f"{method}:{path}:{timestamp}"
    
    signature = hmac.new(
        secret_key.encode(),
        message.encode(),
        hashlib.md5
    ).hexdigest()
    
    return f"HMAC {timestamp}:{signature}"

# Usage
method = "GET"
path = "/api/users"
secret = "your-secret-key"
token = generate_hmac_token(method, path, secret)
print(f"Authorization: {token}")
```

**Node.js**:
```javascript
const crypto = require('crypto');

function generateHmacToken(method, path, secretKey) {
    const timestamp = Math.floor(Date.now() / 1000);
    const message = `${method}:${path}:${timestamp}`;
    
    const hmac = crypto.createHmac('md5', secretKey);
    hmac.update(message);
    const signature = hmac.digest('hex');
    
    return `HMAC ${timestamp}:${signature}`;
}

// Usage
const method = "GET";
const path = "/api/users";
const secret = "your-secret-key";
const token = generateHmacToken(method, path, secret);
console.log(`Authorization: ${token}`);
```

## Build

Build the plugin for C++ from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/hmac_token_validation:plugin_cpp.wasm
```

**Note**: Only C++ implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/hmac_token_validation/tests.textpb \
    --plugin /mnt/bazel-bin/samples/hmac_token_validation/plugin_cpp.wasm

# Using Bazel
bazelisk test --test_output=all //samples/hmac_token_validation:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **Invalid_HMAC_Format** | `Authorization: HMAC invalid_timestamp` (missing `:` separator) | 400 Bad Request with `"Invalid token format: expected 'timestamp:hmac'"` |
| **Missing_Authorization_Header** | No `Authorization` header | 401 Unauthorized with `"Missing Authorization header"` and `WWW-Authenticate: HMAC realm="api"` |
| **Invalid_HMAC_Value** | `Authorization: HMAC 1717000000:invalid_hmac_value` (wrong signature) | 403 Forbidden with `"Invalid HMAC"` |
| **Case_Insensitive_Scheme** | `Authorization: hmac 1717000000:valid_hmac` (lowercase scheme) | 403 Forbidden (scheme accepted, but HMAC validation fails with test data) |
| **Expired_Token** | `Authorization: HMAC 1710000000:hmac_value` (timestamp > 300 seconds old) | 403 Forbidden with `"Token expired"` |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
