# HMAC Auth Token Plugin

This plugin implements URL-based authentication using HMAC (Hash-based Message Authentication Code) signatures. It validates authentication tokens passed as query parameters in request URLs, verifies the HMAC signature matches the path, and removes the token before forwarding the request to the upstream server. Use this plugin when you need to implement signed URLs, protect resources with time-limited or one-time access tokens, or enable secure URL sharing without requiring cookies or headers. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. **URL parsing**: The plugin reads the `:path` pseudo-header and parses it as a URL using Boost.URL:
   - If parsing fails (invalid URL format), the plugin returns a 400 Bad Request response.

3. **Token extraction**: The plugin searches for a `token` query parameter in the URL:
   - If the `token` parameter is missing, the request is rejected with a 403 Forbidden response.
   - If present, the plugin extracts the token value and removes the `token` parameter from the URL.

4. **HMAC signature verification**: The plugin computes the HMAC-SHA256 hash of the URL path (without the token parameter) using a secret key:
   - The plugin compares the computed hash to the token value.
   - If they don't match, the request is rejected with a 403 Forbidden response (indicating an invalid or tampered token).

5. **Token removal**: If the token is valid, the plugin replaces the `:path` header with the URL that has the `token` parameter removed. This prevents the token from being sent to the upstream server.

6. **Success**: If all validations pass, the plugin allows the request to proceed to the upstream server with the cleaned URL.

## Implementation Notes

- **URL parsing**: The `Boost.URL` library is used to parse the URL and handle query parameters directly via `url->params()`.
- **HMAC computation**: Calculates an HMAC-SHA256 signature natively using OpenSSL on the target URL path without the attached `token`.
- **Token removal**: After verifying the signature is valid, the token query parameter is stripped from the `:path` pseudo-header so it doesn't leak upstream.

## Configuration

No configuration required. The secret key is hardcoded in the plugin source.

**Important**: Replace `kSecretKey = "your_secret_key"` with a strong, randomly generated secret in production. The secret must be at least 32 bytes long for security.

## Token Format

The `token` query parameter should contain the HMAC-SHA256 signature of the URL path (without the token parameter itself).

**Token generation process**:
1. Construct the target URL path with all query parameters except `token`
2. Compute HMAC-SHA256(path, secret_key)
3. Convert the result to a hex string
4. Append as `token` query parameter

**Example**:
```
Target URL: /somepage/otherpage?param1=value1&param2=value2
Secret key: your_secret_key

HMAC-SHA256(path): 48277f04685e364e0e3f3c4bfa78cb91293d304bbf196829334cb1c4a741d6b0

Signed URL: /somepage/otherpage?param1=value1&param2=value2&token=48277f04685e364e0e3f3c4bfa78cb91293d304bbf196829334cb1c4a741d6b0
```

**Token generation (Python example)**:
```python
import hmac
import hashlib

def generate_token(path, secret_key):
    """Generate HMAC token for a URL path."""
    signature = hmac.new(
        secret_key.encode(),
        path.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature

path = "/somepage/otherpage?param1=value1&param2=value2"
secret = "your_secret_key"
token = generate_token(path, secret)
signed_url = f"{path}&token={token}"
print(signed_url)
```

## Build

Build the plugin for C++ from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/hmac_authtoken:plugin_cpp.wasm
```

**Note**: Only C++ implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/hmac_authtoken/tests.textpb \
    --plugin /mnt/bazel-bin/samples/hmac_authtoken/plugin_cpp.wasm

# Using Bazel
bazelisk test --test_output=all //samples/hmac_authtoken:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **WithValidHMACToken** | Validates the token, strips it from the path, and forwards the cleaned request upstream. |
| **NoToken** | Rejects the request when the required token parameter is absent. |
| **InvalidToken** | Rejects the request when the provided string fails HMAC verification. |
| **InvalidPathHeader** | Returns a 400 Bad Request if the incoming URL is malformed and cannot be parsed. |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
