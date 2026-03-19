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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Parses the `:path` header, validates the HMAC token, and removes it from the URL before forwarding |

## Key Code Walkthrough

This plugin is only available in C++:

- **Secret key** — The plugin uses a hardcoded secret key for HMAC computation:
  ```cpp
  const std::string kSecretKey = "your_secret_key";
  ```
  **Important**: Replace this with a strong, randomly generated secret key in production. The secret must be kept confidential and must match the key used to generate the tokens.

- **URL parsing** — The plugin parses the `:path` header using Boost.URL:
  ```cpp
  boost::system::result<boost::urls::url> url =
      boost::urls::parse_relative_ref(getRequestHeader(":path")->toString());
  if (!url) {
      sendLocalResponse(400, "", "Error parsing the :path HTTP header.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
  }
  ```
  The `parse_relative_ref` function handles relative URLs (e.g., `/path?query`) and absolute URLs. If parsing fails, a 400 error is returned.

- **Token extraction and removal** — The plugin searches for the `token` query parameter:
  ```cpp
  auto it = url->params().find("token");
  if (it == url->params().end()) {
      sendLocalResponse(403, "", "Access forbidden - missing token.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
  }
  
  const std::string token = (*it).value;
  url->params().erase(it);  // Remove token from URL
  const std::string path = url->buffer();
  ```
  The `params()` method provides access to query parameters. After extracting the token value, it's removed from the URL using `erase()`. The `buffer()` method returns the complete URL string without the token.

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
  The HMAC is computed over the URL path (without the token parameter) and returned as a hex string.

- **Signature verification** — The plugin compares the computed signature to the token:
  ```cpp
  if (computeHmacSignature(path) != token) {
      sendLocalResponse(403, "", "Access forbidden - invalid token.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
  }
  ```

- **Path rewriting** — After validation, the plugin updates the `:path` header:
  ```cpp
  replaceRequestHeader(":path", path);
  ```
  This ensures the upstream server receives the clean URL without the token parameter.

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

| Scenario | Input | Output |
|---|---|---|
| **WithValidHMACToken** | `:path: /somepage/otherpage?param1=value1&param2=value2&token=48277f04685e364e0e3f3c4bfa78cb91293d304bbf196829334cb1c4a741d6b0` | `:path: /somepage/otherpage?param1=value1&param2=value2` (valid token removed, request allowed) |
| **NoToken** | `:path: /admin` (no token parameter) | 403 with `"Access forbidden - missing token.\n"` (token required) |
| **InvalidToken** | `:path: /admin?token=ddssdsdsddfdffddsssd` (invalid token) | 403 with `"Access forbidden - invalid token.\n"` (signature verification failed) |
| **InvalidPathHeader** | `:path: foo:bar` (malformed URL) | 400 with `"Error parsing the :path HTTP header.\n"` (URL parsing failed) |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
