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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_body` | Appends `"foo"` to each chunk of the request body |
| `on_http_response_body` | Appends `"bar"` to each chunk of the response body |

## Key Code Walkthrough

The core logic is identical between the C++ and Rust implementations:

- **Request body modification** — The plugin appends `"foo"` to each request body chunk:
  - **C++** uses `setBuffer(WasmBufferType::HttpRequestBody, chunk_len, 0, "foo")`. The parameters specify:
    - Buffer type: `HttpRequestBody`
    - Offset: `chunk_len` (append after existing content)
    - Length to replace: `0` (insert without replacing)
    - New content: `"foo"`

- **Response body modification** — The plugin appends `"bar"` to each response body chunk:
  - **C++** uses `setBuffer(WasmBufferType::HttpResponseBody, chunk_len, 0, "bar")` with the same offset/length semantics.

- **Chunking semantics** — The `chunk_len` parameter indicates the size of the current chunk. By using `chunk_len` as the offset and `0` as the replacement length, the plugin appends content without removing any existing data. This works regardless of whether the body is transmitted as a single chunk or multiple chunks.

- **End-of-stream flag** — Both callbacks receive an `end_of_stream` parameter that indicates whether this is the final chunk. The plugin ignores this flag and processes all chunks identically.

**Important**: This plugin modifies body content without updating the `Content-Length` header. In production, you would need to either remove the `Content-Length` header to force chunked transfer encoding, or calculate and update the header to reflect the new body size.

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

| Scenario | Input | Output |
|---|---|---|
| **NumChunkWithFileInput** | Request body from `request_body.data` (`1234567890`) split into 5 chunks; Response body from `response_body.data` (`0987654321`) split into 5 chunks | Request: `12foo34foo56foo78foo90foo` (each 2-byte chunk gets `"foo"` appended); Response: `09bar87bar65bar43bar21bar` (each 2-byte chunk gets `"bar"` appended) |
| **NumChunkWithFileInputFileOutput** | Request body from `request_body.data` split into 5 chunks | Request body matches `expected_request_body.data` (`12foo34foo56foo78foo90foo`) |
| **NumChunkWithContentInput** | Request body `1234567890` (inline content) split into 5 chunks | Request: `12foo34foo56foo78foo90foo` (same as file input) |
| **ChunkSizeWithFileInput** | Request body from `request_body.data`, chunked by size (2 bytes) | Request: `12foo34foo56foo78foo90foo` (chunk size produces same result as num_chunks) |
| **ChunkSizeWithContentInput** | Request body `1234567890` (inline content), chunked by size (2 bytes) | Request: `12foo34foo56foo78foo90foo` (chunk size produces same result) |
| **NoChunking** | Three separate request bodies: `"12"`, `"34"`, `"56"` (each processed as a single chunk) | Request bodies: `"12foo"`, `"34foo"`, `"56foo"` (each gets `"foo"` appended once) |

## Available Languages

- [x] [C++](plugin.cc)
- [ ] Rust (not available)
- [ ] Go (not available)
