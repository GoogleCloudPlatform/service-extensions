// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// [START serviceextensions_plugin_zstd_compression]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use zstd::bulk;

const MAX_SIZE_BYTES: usize = 3 * 1024 * 1024; // 3MB limit

// This plugin compresses HTTP responses using zstd when the client
// supports it and the content type is compressible.
proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext::default()) });
}}

#[derive(Default)]
struct MyHttpContext {
    client_supports_zstd: bool,
    should_compress: bool,
    is_chunked_mode: bool,
    headers_modified: bool,
    original_content_length: Option<usize>,
    body_buffer: Vec<u8>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        if let Some(accept_encoding) = self.get_http_request_header("Accept-Encoding") {
            self.client_supports_zstd = should_use_zstd(&accept_encoding);
        }
        Action::Continue
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        if !self.client_supports_zstd {
            return Action::Continue;
        }

        // Do not re-encode if the response is already encoded.
        if let Some(existing_encoding) = self.get_http_response_header("Content-Encoding") {
            if !existing_encoding.is_empty() {
                return Action::Continue;
            }
        }

        let content_type = match self.get_http_response_header("Content-Type") {
            Some(ct) if is_compressible_content_type(&ct) => ct,
            _ => return Action::Continue,
        };

        // Check for Content-Length to distinguish fixed-length vs chunked.
        if let Some(content_length_header) = self.get_http_response_header("Content-Length") {
            let content_length = match content_length_header.parse::<usize>() {
                Ok(len) if len > 0 && len <= MAX_SIZE_BYTES => len,
                _ => return Action::Continue,
            };

            self.original_content_length = Some(content_length);
            self.should_compress = true;
            self.headers_modified = true;

            // Remove Content-Length; it will be recomputed after compression.
            self.set_http_response_header("Content-Length", None);
            self.set_http_response_header("Content-Encoding", Some("zstd"));
            self.add_http_response_header("Vary", "Accept-Encoding");
            let _ = content_type; // silence unused variable if optimized out
        } else {
            // No Content-Length means chunked transfer encoding.
            self.is_chunked_mode = true;
            self.should_compress = true;
            let _ = content_type;
        }

        Action::Continue
    }

    fn on_http_response_body(&mut self, body_size: usize, end_of_stream: bool) -> Action {
        if !self.should_compress {
            return Action::Continue;
        }

        // Buffer the response body so we can compress the full payload.
        if let Some(body) = self.get_http_response_body(0, body_size) {
            self.body_buffer.clear();
            self.body_buffer.extend_from_slice(&body);
        }

        // Abort compression for chunked responses if size exceeds limit.
        if self.is_chunked_mode && body_size > MAX_SIZE_BYTES {
            return self.abort_compression();
        }

        if !end_of_stream {
            // Wait for the full response body.
            return Action::Pause;
        }

        if self.body_buffer.is_empty() {
            return self.abort_compression();
        }

        let compressed = match compress_data(&self.body_buffer) {
            Some(data) => data,
            None => return self.abort_compression(),
        };

        // Only use the compressed version if it is smaller.
        if compressed.len() >= self.body_buffer.len() {
            return self.abort_compression();
        }

        // For chunked responses, set Content-Encoding only if compression
        // is actually applied.
        if self.is_chunked_mode && !self.headers_modified {
            self.set_http_response_header("Content-Encoding", Some("zstd"));
            self.add_http_response_header("Vary", "Accept-Encoding");
            self.headers_modified = true;
        }

        self.set_http_response_body(0, body_size, &compressed);

        if !self.is_chunked_mode {
            self.set_http_response_header(
                "Content-Length",
                Some(&compressed.len().to_string()),
            );
        }

        self.body_buffer.clear();
        Action::Continue
    }
}

impl MyHttpContext {
    // Abort compression and restore headers if they were modified.
    fn abort_compression(&mut self) -> Action {
        self.should_compress = false;
        self.body_buffer.clear();

        if self.headers_modified {
            self.set_http_response_header("Content-Encoding", None);
            self.set_http_response_header("Vary", None);
            if let Some(original_len) = self.original_content_length {
                self.set_http_response_header("Content-Length", Some(&original_len.to_string()));
            }
            self.headers_modified = false;
        }

        Action::Continue
    }
}

// Decide whether zstd should be used based on Accept-Encoding q-values.
fn should_use_zstd(accept_encoding: &str) -> bool {
    let mut zstd_q: f32 = 0.0;
    let mut best_other_q: f32 = 0.0;

    for encoding_part in accept_encoding.split(',') {
        let encoding_part = encoding_part.trim();
        if encoding_part.is_empty() {
            continue;
        }

        let mut parts = encoding_part.split(';');
        let encoding = parts.next().map(str::trim).unwrap_or("");
        if encoding.is_empty() {
            continue;
        }

        let mut q_value: f32 = 1.0;

        for param in parts {
            let param = param.trim();
            if param.len() >= 2
                && (param.starts_with("q=") || param.starts_with("Q="))
            {
                let q_str = &param[2..];
                q_value = q_str.parse::<f32>().unwrap_or(1.0);
                if q_value < 0.0 {
                    q_value = 0.0;
                } else if q_value > 1.0 {
                    q_value = 1.0;
                }
                break;
            }
        }

        if encoding == "zstd" {
            zstd_q = q_value;
        } else if encoding == "br" || encoding == "gzip" || encoding == "deflate" {
            if q_value > best_other_q {
                best_other_q = q_value;
            }
        }
    }

    zstd_q > 0.0 && zstd_q >= best_other_q
}

// Check if the content type is suitable for compression.
fn is_compressible_content_type(ct: &str) -> bool {
    ct.contains("text/")
        || ct.contains("application/json")
        || ct.contains("application/javascript")
        || ct.contains("application/xml")
        || ct.contains("application/xhtml")
        || ct.contains("+json")
        || ct.contains("+xml")
        || ct.contains("svg")
}

fn get_compression_level(input_size: usize) -> i32 {
    if input_size <= 256 * 1024 {
        3
    } else if input_size <= 1024 * 1024 {
        2
    } else {
        1
    }
}

// Compress the given input using the zstd library.
fn compress_data(input: &[u8]) -> Option<Vec<u8>> {
    let level = get_compression_level(input.len());
    bulk::compress(input, level).ok()
}
// [END serviceextensions_plugin_zstd_compression]
