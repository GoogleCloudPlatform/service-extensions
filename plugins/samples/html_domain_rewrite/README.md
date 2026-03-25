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

## Implementation Notes

- **Streaming parser**: Uses the `lol_html` dependency to process chunked HTML body streams resiliently.
- **Selective rewrites**: Triggers string replacements specifically on `<a href="...">` attribute values rather than broad textual replacements.
- **Iterative processing**: Avoids early termination and correctly processes the entire HTML body length across chunks.
- **Shared state management**: Utilizes Rust's `Rc<RefCell<Vec<u8>>>` to sync parsing output states between the context and rewriter effectively.

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

| Scenario | Description |
|---|---|
| **DomainRewriteFooOutside<a>** | Replaces domain occurrences strictly within linked href attributes, ignoring instances in text blocks or other element IDs. |

**Important note**: The `lol_html` rewriter normalizes HTML attributes by adding quotes around unquoted attribute values. In the test:
- Input: `<a href=https://foo.com>`
- Output: `<a href="https://bar.com">` (domain rewritten, quotes added)

This is standard HTML normalization and does not affect browser behavior.

## Available Languages

- [x] [Rust](plugin.rs)
- [ ] C++ (not available)
- [ ] Go (not available)
