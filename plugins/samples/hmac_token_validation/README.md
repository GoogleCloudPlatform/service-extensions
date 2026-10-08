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

## Implementation Notes

- **Header validation**: Verifies the presence of the `Authorization` header and ensures it uses the `HMAC` scheme.
- **Token decomposition**: Safely splits the token payload into timestamp and signature components.
- **Cryptographic verification**: Constructs a message from the HTTP method, path, and timestamp, then verifies its HMAC-MD5 signature utilizing OpenSSL.
- **Temporal constraints**: Uses `absl::Now()` to enforce a maximum token age of 5 minutes (300 seconds).

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

| Scenario | Description |
|---|---|
| **Invalid_HMAC_Format** | Responds with 400 Bad Request when the token string is not formatted properly. |
| **Missing_Authorization_Header** | Responds with 401 Unauthorized when the required authorization header is omitted. |
| **Invalid_HMAC_Value** | Responds with 403 Forbidden when the token signature fails validation. |
| **Case_Insensitive_Scheme** | Accepts differently cased `hmac` schemes but correctly enforces signature validity. |
| **Expired_Token** | Responds with 403 Forbidden when the token's timestamp is older than the allowed expiration period. |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
