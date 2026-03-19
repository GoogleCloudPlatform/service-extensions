# HTML Domain Rewrite Plugin

This plugin demonstrates selective HTML rewriting by replacing domain names only within specific HTML elements. It uses the `lol_html` streaming HTML parser to find all `<a>` tags with `href` attributes and rewrite `foo.com` to `bar.com`, while leaving other occurrences of the domain name unchanged. Use this plugin when you need to migrate domains, implement link rewriting for proxied content, or transform HTML responses without affecting non-link content. It operates during the **response body** processing phase.

## How It Works

1. The proxy receives chunks of an HTTP response body from the upstream server and invokes the plugin's `on_http_response_body` callback for each chunk.

2. **HTML parsing and rewriting**:
   - The plugin uses the `lol_html` crate's `HtmlRewriter` to parse HTML in a streaming fashion.
   - The rewriter is configured with an element content handler that matches `<a>` tags with `href` attributes (selector: `a[href]`).
   - For each chunk, the plugin calls `rewriter.write(&body_bytes)` to parse and process the HTML.
   - The rewriter maintains internal state across chunks, allowing it to correctly parse HTML elements that are split across chunk boundaries.

3. **Domain rewriting**:
   - When the rewriter encounters an `<a href="...">` tag, it reads the `href` attribute value.
   - The plugin replaces all occurrences of `"foo.com"` with `"bar.com"` in the href value using Rust's `String::replace()`.
   - If the href was modified, the plugin updates the attribute using `el.set_attribute("href", &modified_href)`.
   - Domain names outside of `<a href>` attributes (e.g., in text content, comments, or other attributes) are not modified.

4. **Output buffering**:
   - As the rewriter parses HTML, it writes modified content to an `output_sink` (a shared `Vec<u8>` buffer).
   - The plugin reads from the output buffer and calls `set_http_response_body()` to replace the original response body with the modified HTML.
   - After sending data to the client, the plugin clears the output buffer to avoid memory growth.

5. **Error handling**: If the rewriter encounters an error, the plugin sends a 500 Internal Server Error response instead of panicking, avoiding plugin crashes.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | No-op (returns `Continue`); included for completeness |
| `on_http_response_body` | Parses and rewrites HTML chunks, replacing `foo.com` with `bar.com` in `<a href>` attributes |

## Key Code Walkthrough

This plugin is only available in Rust and demonstrates selective HTML element modification:

- **HtmlRewriter initialization** — The rewriter is created in `MyHttpContext::new()` with an element content handler:
  ```rust
  element_content_handlers: vec![element!("a[href]", move |el| {
      let href = el.get_attribute("href").unwrap();
      let modified_href = href.replace("foo.com", "bar.com");
      if modified_href != href {
          el.set_attribute("href", &modified_href).unwrap();
      }
      Ok(())
  })]
  ```
  - **Selector**: `"a[href]"` matches all `<a>` tags that have an `href` attribute.
  - **Domain replacement**: `href.replace("foo.com", "bar.com")` replaces all occurrences of the old domain with the new domain in the attribute value.
  - **Conditional update**: The attribute is only updated if the href was actually modified, avoiding unnecessary writes.

- **Selective rewriting** — The plugin only modifies `href` attributes of `<a>` tags:
  - Text content containing `"foo.com"` (e.g., `<p>Visit foo.com</p>`) is **not** modified.
  - Other attributes containing `"foo.com"` (e.g., `<div id="foo">`) are **not** modified.
  - Only the href values of anchor tags are rewritten.

- **Streaming processing** — The plugin processes the response body as it arrives:
  ```rust
  fn on_http_response_body(&mut self, body_size: usize, _: bool) -> Action {
      if let Some(body_bytes) = self.get_http_response_body(0, body_size) {
          self.parse_chunk(body_bytes)?;
      }
      self.set_http_response_body(0, body_size, self.output.borrow().as_slice());
      self.output.borrow_mut().clear();
      return Action::Continue;
  }
  ```
  Unlike the `content_injection` sample, this plugin does **not** use early termination. It processes the entire response body to find all `<a href>` tags.

- **Shared state management** — The plugin uses `Rc<RefCell<Vec<u8>>>` to share the output buffer between the HTTP context and the rewriter's output sink:
  ```rust
  let output = Rc::new(RefCell::new(Vec::new()));
  // ...
  output_sink: output,  // Shared with rewriter
  ```

- **Error handling** — The plugin avoids panicking by sending a 500 error response:
  ```rust
  if let Err(e) = self.parse_chunk(body_bytes) {
      self.send_http_response(
          500,
          vec![],
          Some(&format!("Error while writing to HtmlRewriter: {}", e).into_bytes()),
      );
      return Action::Pause;
  }
  ```

## Configuration

No configuration required. The source domain (`foo.com`) and target domain (`bar.com`) are hardcoded in the element content handler.

To rewrite different domains, modify the `replace()` call:
```rust
let modified_href = href.replace("old-domain.com", "new-domain.com");
```

## Build

Build the plugin for Rust from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/html_domain_rewrite:plugin_rust.wasm
```

**Note**: Only Rust implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/html_domain_rewrite/tests.textpb \
    --plugin /mnt/bazel-bin/samples/html_domain_rewrite/plugin_rust.wasm

# Using Bazel
bazelisk test --test_output=all //samples/html_domain_rewrite:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Input | Output |
|---|---|---|
| **DomainRewriteFooOutside<a>** | HTML with `<p>Instances of "foo.com" here should not change</p>`, `<div id=foo>`, and two `<a href=https://foo.com>` links, split into 10 chunks | Text content `"foo.com"` unchanged; `<div id=foo>` unchanged; both `<a href>` attributes rewritten to `https://bar.com` with quotes added around attribute value |

**Important note**: The `lol_html` rewriter normalizes HTML attributes by adding quotes around unquoted attribute values. In the test:
- Input: `<a href=https://foo.com>`
- Output: `<a href="https://bar.com">` (domain rewritten, quotes added)

This is standard HTML normalization and does not affect browser behavior.

## Available Languages

- [x] [Rust](plugin.rs)
- [ ] C++ (not available)
- [ ] Go (not available)
