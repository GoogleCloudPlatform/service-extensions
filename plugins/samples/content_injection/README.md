# Content Injection Plugin

This plugin demonstrates advanced HTML rewriting by injecting a JavaScript script tag into the `<head>` section of HTML responses. It uses the `lol_html` streaming HTML parser/rewriter to efficiently process and modify HTML content as it flows through the proxy, even when the HTML is split across multiple chunks. Use this plugin when you need to inject analytics scripts, security headers, or other content into HTML responses without buffering the entire response body. It operates during the **response body** processing phase.

## How It Works

1. The proxy receives chunks of an HTTP response body from the upstream server and invokes the plugin's `on_http_response_body` callback for each chunk.

2. **HTML parsing and rewriting**:
   - The plugin uses the `lol_html` crate's `HtmlRewriter` to parse HTML in a streaming fashion. The rewriter is configured with an element content handler that matches the `<head>` tag.
   - For each chunk, the plugin calls `rewriter.write(&body_bytes)` to parse and process the HTML. The rewriter maintains internal state across chunks, allowing it to correctly parse HTML elements that are split across chunk boundaries.
   - When the rewriter encounters a `<head>` tag, it prepends the script tag `<script src="https://www.foo.com/api.js"></script>` and sets a `completed` flag to `true`.

3. **Output buffering**:
   - As the rewriter parses HTML, it writes modified content to an `output_sink` (a shared `Vec<u8>` buffer). The rewriter only outputs complete HTML elements (e.g., if it parses `"<di"`, nothing is written until the next chunk completes the element as `"<div>"`).
   - The plugin reads from the output buffer and calls `set_http_response_body()` to replace the original response body with the modified HTML.
   - After sending data to the client, the plugin clears the output buffer to avoid memory growth.

4. **Early termination**:
   - Once the `completed` flag is set (after injecting the script), the plugin calls `rewriter.end()` to flush any buffered HTML and stops processing further chunks. This optimization avoids unnecessary parsing and rewriting of the rest of the HTML document.
   - Subsequent `on_http_response_body` calls return immediately if `completed` is `true`.

5. **Chunked processing**:
   - The plugin processes the response body in 500-byte chunks (controlled by `chunk_size`) to balance memory usage and processing efficiency, even when the underlying proxy delivers larger or smaller chunks.

## Implementation Notes

- **Streaming HTML parser**: Utilizes the `lol_html` crate's `HtmlRewriter` to process HTML structure across potentially split response chunks.
- **Shared state capabilities**: Rust leverages `Rc<RefCell<T>>` to manage the modified HTML buffer and completion flags across callback executions.
- **Chunked processing strategy**: Reads the response body in configurable chunk sizes to maintain steady memory overhead.
- **Early termination**: Flushes buffers and stops executing further HTML rewrites as soon as the intended injection completes successfully.

## Configuration

No configuration required. The injected script URL (`https://www.foo.com/api.js`) is hardcoded in the element content handler.

## Test Data Files

The tests use the following data files located in `samples/content_injection/`:

- **`response_body.data`**: Input HTML (1.1 KB) containing a basic HTML document with a `<head>` section and multiple `<h1>` and `<p>` elements.
- **`expected_response_body.data`**: Expected output after injecting the script tag into the `<head>` section.

Both files contain identical HTML except that `expected_response_body.data` includes the injected `<script src="https://www.foo.com/api.js"></script>` tag at the beginning of the `<head>` section.

## Build

Build the plugin for Rust from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/content_injection:plugin_rust.wasm
```

**Note**: Only Rust implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/content_injection/tests.textpb \
    --plugin /mnt/bazel-bin/samples/content_injection/plugin_rust.wasm

# Using Bazel
bazelisk test --test_output=all //samples/content_injection:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **ContentInjection** | Successfully injects the script element exactly into the `<head>` block of an HTML response. |
| **LargeBody1Chunk** | Verifies performance and correctness over a large body processed as a single chunk. |
| **LargeBody10Chunks** | Verifies performance and correctness over a large body dynamically split into 10 chunks. |
| **LargeBody50Chunks** | Verifies system stability when a large response is excessively chunked. |
| **LargeBody100Chunks** | Analyzes CPU constraints under heavy response chunking loads. |

## Available Languages

- [x] [Rust](plugin.rs)
- [ ] C++ (not available)
- [ ] Go (not available)
