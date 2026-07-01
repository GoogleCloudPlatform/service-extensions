# Ad Insertion Plugin

This plugin modifies HTTP response bodies to dynamically insert Google Ad Manager (GAM) ad units into HTML content. It operates during the **response body** processing phase by buffering the full HTML body and injecting the `gpt.js` library along with specific ad containers based on configuration markers. It reads ad placements from a configuration payload during **plugin initialization** and prevents infinite loops by avoiding ad insertion on requests for ad scripts themselves. Use this plugin when you need to centrally inject and manage ad placeholders across backend services without modifying their application code.

## Implementation Notes

- **Configuration parsing**: Loads a CSV-like text configuration at module initialization to define the GPT library URL and various ad slot configurations (slot path, size, relative marker, and placement).
- **Infinite loop prevention**: Inspects the `:path` header to identify and skip ad requests (e.g., `/ads/`) to avoid injecting ads into ad script responses.
- **Content type matching**: Checks the `Content-Type` response header to ensure manipulation only occurs on `text/html` payloads.
- **Body buffering**: Returns `StopIterationAndBuffer` until the end of the stream to ensure the entire HTML document is available, avoiding issues with split HTML tags across chunks.
- **Content-Length removal**: Safely removes the `Content-Length` response header because the overall size of the body increases upon ad insertion.
- **Single pass insertion**: Matches HTML markers and prepares all insertions, applying them from bottom to top to preserve accurate string positions.

## Configuration Parsing

All implementations parse a CSV-like text format:

- **C++**:
  ```cpp
  for (absl::string_view line : absl::StrSplit(config_str, '\n')) {
      absl::string_view stripped = absl::StripAsciiWhitespace(line);
      if (stripped.empty() || stripped[0] == '#') continue;
      
      std::vector<absl::string_view> parts = absl::StrSplit(stripped, ',');
      // Processes directives based on parts[0]...
  }
  ```
  Uses Abseil for string splitting and trims whitespace to populate ad configurations.

- **Rust**:
  Uses Rust's iterator-based string processing and `split(',')` to parse the same payload format into custom configuration structures.

### Configuration Format

The plugin requires a configuration file with comma-separated values. 

**Example configuration** (`tests.config`):
```
gpt_url, https://custom.pubads.g.doubleclick.net/tag/js/gpt.js
inject_gpt, true
ad, custom_header, /9999/custom_header_ad, 970x250, true, <header>
ad, custom_footer, /9999/custom_footer_ad, 728x90, false, <footer>
```

**Format rules**:
- Format: `directive, value1, value2, ...` (comma-separated with optional whitespace)
- Config directives supported:
  - `gpt_url, <url>`
  - `inject_gpt, <true|false>`
  - `ad, <position_id>, <gam_slot_path>, <size>, <insert_before_bool>, <html_marker>`
- Lines starting with `#` are comments.
- Empty lines are ignored.

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/ad_insertion:plugin_rust.wasm

# C++
bazelisk build //samples/ad_insertion:plugin_cpp.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/ad_insertion/tests.textpb \
    --plugin /mnt/bazel-bin/samples/ad_insertion/plugin_cpp.wasm \
    --config /mnt/samples/ad_insertion/tests.config

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/ad_insertion:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **CustomConfigAdInsertion** | Injects the GPT library and properly sizes and places GAM ad units relative to configured HTML markers. |
| **NoAdInsertionWhenMarkersMissingWithCustomConfig** | Injects the GPT script but skips ad insertion if the configured markers are missing from the HTML body. |
| **NoAdInsertionForNonHtml** | Ignores the response entirely if the `Content-Type` is not `text/html`. |
| **NoAdInsertionForAdRequest** | Skips the request early if the request path looks like an ad request to avoid infinite loops. |
| **ContentLengthRemoved** | Successfully strips the `Content-Length` header for HTML responses to account for body sizing changes. |
| **GptLibraryFallbackToBody** | Falls back to injecting the GPT library into the `<body>` if `<head>` is missing. |

## Available Languages

- [x] [C++](plugin.cc)
- [x] [Rust](plugin.rs)
