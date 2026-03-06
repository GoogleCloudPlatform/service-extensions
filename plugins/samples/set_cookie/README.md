# Set Cookie Plugin

This plugin implements automatic session management by detecting if a session ID cookie exists in incoming requests and creating one if it doesn't. When a request arrives without a valid session cookie, the plugin generates a random session ID and sets it via a `Set-Cookie` response header. Use this plugin when you need to implement session tracking, ensure all users have session identifiers, or add stateful behavior to stateless backends. It operates during both the **request headers** and **response headers** processing phases.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.
2. The plugin reads the `Cookie` header and performs security validations:
   - Checks if the header exists (returns nullopt if missing)
   - Validates header size (max 4KB) to prevent DoS attacks
   - Validates cookie format and structure
3. **Cookie parsing**: If valid, the plugin splits the `Cookie` header by `; ` (semicolon-space) to separate individual cookies, then splits each cookie by `=` to extract name-value pairs. Malformed cookies (without `=`) are skipped.
4. **Session ID extraction**: If `my_cookie` is found, its value is validated:
   - Must not be empty
   - Maximum length of 128 characters
   - Must contain only alphanumeric characters
   
   If valid, the session ID is stored for later use. Otherwise, the plugin records that no valid session ID exists.
5. When the upstream response arrives, the proxy invokes the plugin's `on_http_response_headers` callback.
6. **If valid session ID exists** (detected in request phase):
   - The plugin logs: `"This current request is for the existing session ID: {id}"`
   - No `Set-Cookie` header is added (client already has a valid session)
7. **If no valid session ID** (not found or invalid in request):
   - The plugin generates a new random session ID using a cryptographically secure random number generator
   - Attempts to add a `Set-Cookie` response header: `my_cookie={new_id}; Path=/; HttpOnly`
   - Verifies the operation success (logs error if header addition fails)
   - Logs: `"New session ID created for the current request: {new_id}"`
8. The response is forwarded to the client with the new session cookie (if successfully created).

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Parses and validates the `Cookie` header to detect an existing session ID |
| `on_http_response_headers` | Adds a `Set-Cookie` header if no valid session ID was found in the request |

## Key Code Walkthrough

This plugin is only available in C++:

- **Random number generation** — Uses Abseil's secure random generator:
  ```cpp
  class MyRootContext : public RootContext {
   private:
    absl::BitGen bitgen_;
   public:
    uint64_t generateRandom() { return absl::Uniform<uint64_t>(bitgen_); }
  };
  ```
  - `absl::BitGen` provides cryptographically strong random numbers
  - `absl::Uniform<uint64_t>` generates a random 64-bit unsigned integer
  - The generator is stored in the root context for reuse across requests

- **Cookie parsing** — Extracts session ID from `Cookie` header:
  ```cpp
  static std::optional<std::string> getSessionIdFromCookie() {
    const auto cookies = getRequestHeader("Cookie")->toString();
    for (absl::string_view sp : absl::StrSplit(cookies, "; ")) {
      const std::pair<std::string, std::string> cookie =
          absl::StrSplit(sp, absl::MaxSplits('=', 1));
      if (cookie.first == kCookieName) {
        return cookie.second;
      }
    }
    return std::nullopt;
  }
  ```
  - Splits on `"; "` to separate multiple cookies
  - Splits each cookie on `=` with max splits of 1 (handles values containing `=`)
  - Returns `std::nullopt` if cookie not found

- **Session detection** — Stores session ID for use in response phase:
  ```cpp
  FilterHeadersStatus onRequestHeaders(...) override {
    session_id_ = getSessionIdFromCookie();
    return FilterHeadersStatus::Continue;
  }
  ```
  - Member variable `session_id_` persists across callbacks

- **Conditional cookie setting** — Only sets cookie if session ID doesn't exist:
  ```cpp
  FilterHeadersStatus onResponseHeaders(...) override {
    if (session_id_.has_value()) {
      LOG_INFO("This current request is for the existing session ID: " + *session_id_);
    } else {
      const std::string new_session_id = std::to_string(root_->generateRandom());
      LOG_INFO("New session ID created for the current request: " + new_session_id);
      addResponseHeader("Set-Cookie",
          absl::StrCat(kCookieName, "=", new_session_id, "; Path=/; HttpOnly"));
    }
    return FilterHeadersStatus::Continue;
  }
  ```
  - Checks if `session_id_` has a value (was found in request)
  - If not, generates new ID and adds `Set-Cookie` header

- **Cookie attributes** — The generated cookie includes security attributes:
  - `Path=/` — Cookie is sent for all paths on the domain
  - `HttpOnly` — Cookie cannot be accessed by JavaScript (prevents XSS attacks)

## Configuration

No configuration required. The cookie name (`my_cookie`) is hardcoded as a constant.

**Customization**:

1. **Change cookie name**:
   ```cpp
   constexpr absl::string_view kCookieName = "session_id";
   ```

2. **Add more cookie attributes**:
   ```cpp
   addResponseHeader("Set-Cookie",
       absl::StrCat(kCookieName, "=", new_session_id, 
                    "; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600"));
   ```
   - `Secure` — Only send over HTTPS
   - `SameSite=Strict` — Prevent CSRF attacks
   - `Max-Age=3600` — Cookie expires in 1 hour

3. **Use UUID instead of random number**:
   ```cpp
   // Generate UUID-like string
   std::string generateUUID() {
       uint64_t high = root_->generateRandom();
       uint64_t low = root_->generateRandom();
       return absl::StrCat(absl::Hex(high), "-", absl::Hex(low));
   }
   ```

4. **Add domain restriction**:
   ```cpp
   addResponseHeader("Set-Cookie",
       absl::StrCat(kCookieName, "=", new_session_id, 
                    "; Domain=.example.com; Path=/; HttpOnly"));
   ```

## Build

Build the plugin for C++ from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/set_cookie:plugin_cpp.wasm
```

**Note**: Only C++ implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/set_cookie/tests.textpb \
    --plugin /mnt/bazel-bin/samples/set_cookie/plugin_cpp.wasm

# Using Bazel
bazelisk test --test_output=all //samples/set_cookie:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Request Input | Response Output |
|---|---|---|
| **WihSessionIdSetKeepTheSameAndLog** | `Cookie: some-cookie=some-value; my_cookie=999999999` (session cookie present) | No `Set-Cookie` header; Log: `"This current request is for the existing session ID: 999999999"` |
| **WihNoSessionIdCreateOneAndLog** | `Cookie: some-cookie=some-value; other-cookie=other-value` (no session cookie) | `Set-Cookie: my_cookie={random_number}; Path=/; HttpOnly`; Log: `"New session ID created for the current request: {random_number}"` |

**Note**: Test names have typos (`Wih` should be `With`). The functionality is correct despite the typos.

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)

## Use Cases

1. **Session tracking**: Automatically assign session IDs to all users for analytics or personalization.

2. **Stateful wrappers**: Add session management to stateless backends without modifying them.

3. **User identification**: Track unique visitors without requiring login.

4. **A/B testing**: Assign users to test groups using session IDs.

5. **Rate limiting**: Use session IDs as keys for per-user rate limits.
