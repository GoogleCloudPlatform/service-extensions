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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_response_body` | Parses and rewrites HTML chunks, injecting the script tag when the `<head>` element is encountered |

## Key Code Walkthrough

This plugin is only available in Rust and demonstrates advanced patterns:

- **HtmlRewriter initialization** — The rewriter is created in `MyHttpContext::new()` with:
  - **Element content handler**: `element!("head", move |el| { ... })` registers a handler that matches `<head>` tags. When matched, it prepends the script tag using `el.prepend("<script src=\"https://www.foo.com/api.js\"></script>", ContentType::Html)`.
  - **Output sink**: `SharedRewriterOutputSink` wraps a shared `Rc<RefCell<Vec<u8>>>` buffer that collects the rewritten HTML as the parser processes it.

- **Shared state management** — The plugin uses `Rc<RefCell<T>>` to share mutable state between the HTTP context and the rewriter's closures:
  - **`output: Rc<RefCell<Vec<u8>>>`** — Stores the modified HTML as the rewriter produces it. The `Rc` (reference-counted pointer) allows multiple references (HTTP context and output sink), while `RefCell` enables runtime-checked mutable borrowing.
  - **`completed: Rc<RefCell<bool>>`** — Tracks whether the script has been injected. This flag is set inside the element handler closure and checked in the HTTP context to optimize processing.

- **Chunked parsing** — In `on_http_response_body`, the plugin iterates through the response body in 500-byte chunks:
  ```rust
  for start_index in (0..body_size).step_by(chunk_size) {
      if let Some(body_bytes) = self.get_http_response_body(start_index, chunk_size) {
          self.parse_chunk(body_bytes)?;
          if *self.completed.borrow() == true {
              self.end_rewriter()?;
              // Replace section [0, start_index + chunk_size) with modified HTML
              self.set_http_response_body(0, start_index + chunk_size, self.output.borrow().as_slice());
              self.output.borrow_mut().clear();
              return Action::Continue;
          }
      }
  }
  ```
  This approach allows the plugin to process large responses incrementally without buffering the entire body.

- **Rewriter lifecycle** — The `HtmlRewriter` persists across multiple `on_http_response_body` calls:
  - **`rewriter.write(&body_bytes)`** — Processes a chunk of HTML, invoking registered handlers and writing output to the sink.
  - **`rewriter.end()`** — Flushes any buffered incomplete HTML elements to the output sink as plain text. This is called after the `<head>` tag is processed to ensure all pending output is written.
  - The rewriter is stored as `Option<HtmlRewriter>` and is consumed (taken) when `end()` is called to finalize processing.

- **Error handling** — The plugin avoids panicking by sending a 500 Internal Server Error response if the rewriter encounters an error:
  ```rust
  if let Err(e) = self.parse_chunk(body_bytes) {
      self.send_http_response(500, vec![], Some(&format!("Error while writing to HtmlRewriter: {}", e).into_bytes()));
      return Action::Pause;
  }
  ```

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

| Scenario | Input | Output |
|---|---|---|
| **ContentInjection** | HTML response with `<head><title>Page Title</title></head>`, split into 10 chunks | `<head><script src="https://www.foo.com/api.js"></script><title>Page Title</title></head>` (script injected at the beginning of `<head>`) |
| **LargeBody1Chunk** | 1.1 KB HTML from `response_body.data` as a single chunk | HTML matching `expected_response_body.data` with script injected (benchmark test) |
| **LargeBody10Chunks** | Same HTML split into 10 chunks | Same output (demonstrates correct handling of chunked HTML, benchmark test) |
| **LargeBody50Chunks** | Same HTML split into 50 chunks | Same output (benchmark test showing marginal CPU increase with more chunks) |
| **LargeBody100Chunks** | Same HTML split into 100 chunks | Same output (benchmark test showing CPU usage remains low) |

## Available Languages

- [x] [Rust](plugin.rs)
- [ ] C++ (not available)
- [ ] Go (not available)
