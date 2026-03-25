# Body Chunking Plugin

This plugin demonstrates how to process HTTP request and response bodies in chunks by appending fixed strings to each chunk. It adds `"foo"` to the end of every request body chunk and `"bar"` to the end of every response body chunk. Use this plugin when you need to understand chunked body processing, implement streaming transformations, or modify body content as it flows through the proxy. It operates during the **request body** and **response body** processing phases.

## How It Works

1. **Request body processing**: When the proxy receives a chunk of the request body from the client, it invokes the plugin's `on_http_request_body` callback.
   - The plugin reads the current chunk length.
   - The plugin appends `"foo"` to the end of the chunk using `setBuffer` (C++) or `set_http_request_body` (Rust).
   - The plugin returns `FilterDataStatus::Continue`, allowing the modified chunk to be forwarded to the upstream server.

2. **Response body processing**: When the proxy receives a chunk of the response body from the upstream server, it invokes the plugin's `on_http_response_body` callback.
   - The plugin reads the current chunk length.
   - The plugin appends `"bar"` to the end of the chunk using `setBuffer` (C++) or `set_http_response_body` (Rust).
   - The plugin returns `FilterDataStatus::Continue`, allowing the modified chunk to be forwarded to the client.

3. **Chunking behavior**: The test file demonstrates that the plugin works correctly with different chunking strategies:
   - **Multiple chunks**: When a 10-byte body (`"1234567890"`) is split into 5 chunks of 2 bytes each (`"12"`, `"34"`, `"56"`, `"78"`, `"90"`), the plugin appends `"foo"` to each chunk, resulting in `"12foo34foo56foo78foo90foo"`.
   - **Single chunk**: When the entire body is processed as a single chunk, the plugin appends `"foo"` once.

## Implementation Notes

- **Chunked body modification**: The plugin appends a fixed string to both request and response body chunks as they stream through the proxy.
- **Buffer editing offsets**: The chunk length is used as the offset for appending data, ensuring existing content is not replaced.
- **Content-Length considerations**: Modifying body content length without updating the `Content-Length` header requires the proxy to handle chunked transfer encoding (not natively handled by this sample).

## Configuration

No configuration required. The strings `"foo"` and `"bar"` are hardcoded in the plugin source.

## Test Data Files

The tests use the following data files located in `samples/body_chunking/`:

- **`request_body.data`**: Input request body containing `1234567890` (10 bytes)
- **`response_body.data`**: Input response body containing `0987654321` (10 bytes)
- **`expected_request_body.data`**: Expected request body after processing: `12foo34foo56foo78foo90foo` (25 bytes when chunked into 5 chunks of 2 bytes each)

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# C++
bazelisk build //samples/body_chunking:plugin_cpp.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/body_chunking/tests.textpb \
    --plugin /mnt/bazel-bin/samples/body_chunking/plugin_cpp.wasm

# Using Bazel
bazelisk test --test_output=all //samples/body_chunking:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **NumChunkWithFileInput** | Successfully appends the corresponding strings to each chunk of the request and response bodies. |
| **NumChunkWithFileInputFileOutput** | Verifies that a request body split into multiple chunks matches the expected concatenated output. |
| **NumChunkWithContentInput** | Verifies inline content matches file input behavior. |
| **ChunkSizeWithFileInput** | Verifies that chunking by explicit sizes produces the same results as chunking by number of chunks. |
| **ChunkSizeWithContentInput** | Verifies chunk size behavior with inline string content. |
| **NoChunking** | Correctly appends the configured string when the body is sent as a single continuous chunk. |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
