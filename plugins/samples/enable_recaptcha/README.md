# Enable reCAPTCHA Plugin

This plugin demonstrates how to enable Google reCAPTCHA Enterprise on HTML pages by injecting the appropriate reCAPTCHA script tag into the `<head>` section of HTML responses. It supports both reCAPTCHA Session Tokens (WAF integration) and reCAPTCHA Actions, using streaming HTML parsing to efficiently modify responses without buffering the entire body. Use this plugin when you need to add bot protection to web applications, implement reCAPTCHA without modifying application code, or centralize reCAPTCHA deployment across multiple services. It operates during the **response body** processing phase, with configuration loading during **plugin initialization**.

**Warning**: This plugin demonstrates the technical capability to inject reCAPTCHA scripts. It is not a replacement for reading the official reCAPTCHA documentation or following complete integration guides. Always refer to the [official reCAPTCHA documentation](https://developers.google.com/recaptcha) for proper implementation.

## How It Works

1. **Plugin initialization**: When the plugin starts, the proxy invokes `on_configure`:
   - The plugin reads a JSON configuration file containing two fields: `recaptcha_key_type` (`"SESSION"` or `"ACTION"`) and `recaptcha_key_value` (the reCAPTCHA site key).
   - The plugin validates that `recaptcha_key_type` is either `"SESSION"` or `"ACTION"`. Invalid values cause the plugin to panic.
   - The plugin stores the configuration in an `Rc<RefCell<RecaptchaConfig>>` for sharing with HTTP contexts.

2. **HTTP context creation**: When an HTTP response arrives, the plugin creates an `HtmlRewriter` configured with an element content handler that matches the `<head>` tag:
   - **For `SESSION` tokens**: The handler prepends `<script src="https://www.google.com/recaptcha/enterprise.js?render=&waf={key}" async defer></script>` to the `<head>` element.
   - **For `ACTION` tokens**: The handler prepends `<script src="https://www.google.com/recaptcha/enterprise.js?render={key}"></script>` to the `<head>` element.

3. **Response body processing**: As response body chunks arrive, the plugin invokes `on_http_response_body`:
   - The plugin processes the HTML in 500-byte chunks using the `lol_html` streaming parser.
   - When the `<head>` tag is encountered, the rewriter injects the reCAPTCHA script and sets the `completed_script_injection` flag to `true`.
   - Once the flag is set, the plugin calls `rewriter.end()` to finalize the rewriter and stops processing further chunks.
   - The plugin replaces the original response body with the modified HTML.

4. **Error handling**: If the rewriter encounters an error, the plugin logs the error and returns `Action::Continue` instead of panicking, avoiding plugin crashes.

## Implementation Notes

- **Configuration parsing**: Parses a JSON configuration at initialization to determine the reCAPTCHA key type and value.
- **Dynamic handler generation**: Dynamically constructs the script tag injection string based on whether the token is a `SESSION` or `ACTION` type.
- **Streaming integration**: Uses the `lol_html` crate to parse HTML chunks incrementally and injects the script into the `<head>` element.
- **Early termination**: Halts the `HtmlRewriter` early as soon as the target tag is successfully modified.

## Configuration

The plugin expects a JSON configuration file with the following structure:

```json
{
  "recaptcha_key_type": "SESSION",
  "recaptcha_key_value": "1234-abcd"
}
```

**Configuration fields**:
- **`recaptcha_key_type`** (required): Either `"SESSION"` (for WAF/session tokens) or `"ACTION"` (for score-based actions). Invalid values cause the plugin to panic.
- **`recaptcha_key_value`** (required): Your reCAPTCHA Enterprise site key.

**Example configurations**:
- **Session token** (`session_key.config`):
  ```json
  {
    "recaptcha_key_type": "SESSION",
    "recaptcha_key_value": "1234-abcd"
  }
  ```
  Injects: `<script src="https://www.google.com/recaptcha/enterprise.js?render=&waf=1234-abcd" async defer></script>`

- **Action token** (`action_key.config`):
  ```json
  {
    "recaptcha_key_type": "ACTION",
    "recaptcha_key_value": "1234-abcd"
  }
  ```
  Injects: `<script src="https://www.google.com/recaptcha/enterprise.js?render=1234-abcd"></script>`

## Test Data Files

The tests use the following data files located in `samples/enable_recaptcha/`:

- **`response_body.data`**: Input HTML (361 bytes) containing a login form without reCAPTCHA.
- **`session_key_expected_response_body.data`**: Expected output after injecting SESSION token script.
- **`action_key_expected_response_body.data`**: Expected output after injecting ACTION token script.
- **`session_key.config`**: JSON config for SESSION token test.
- **`action_key.config`**: JSON config for ACTION token test.

## Build

Build the plugin for Rust from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/enable_recaptcha:plugin_rust.wasm
```

**Note**: Only Rust implementation is available for this plugin.

## Test

Run the unit tests defined in the test files:

```bash
# Using Docker (recommended) - SESSION token test
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/enable_recaptcha/session_tests.textpb \
    --plugin /mnt/bazel-bin/samples/enable_recaptcha/plugin_rust.wasm \
    --config /mnt/samples/enable_recaptcha/session_key.config

# Using Docker (recommended) - ACTION token test
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/enable_recaptcha/action_tests.textpb \
    --plugin /mnt/bazel-bin/samples/enable_recaptcha/plugin_rust.wasm \
    --config /mnt/samples/enable_recaptcha/action_key.config

# Using Bazel (all tests)
bazelisk test --test_output=all //samples/enable_recaptcha:tests
```

## Expected Behavior

Derived from test files:

| Scenario | Description |
|---|---|
| **Enable reCAPTCHA session** (`session_tests.textpb`) | Injects a session-based reCAPTCHA script tag into a chunked HTML response body. |
| **Enable reCAPTCHA action** (`action_tests.textpb`) | Injects an action-based reCAPTCHA script tag into a chunked HTML response body. |

## Available Languages

- [x] [Rust](plugin.rs)
- [ ] C++ (not available)
- [ ] Go (not available)
