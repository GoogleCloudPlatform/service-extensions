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
#include <algorithm>
#include <string>
#include <string_view>

#include "absl/strings/ascii.h"
#include "absl/strings/match.h"
#include "absl/strings/numbers.h"
#include "absl/strings/str_split.h"
#include "proxy_wasm_intrinsics.h"
#include "zstd.h"

constexpr size_t kMaxSizeBytes = 3 * 1024 * 1024;  // 3MB limit
constexpr int kZstdCompressionLevel = 3;

// RAII wrapper for Zstd compression context.
class ZstdContext {
 public:
  ZstdContext() : cctx_(ZSTD_createCCtx()) {
    if (cctx_) {
      ZSTD_CCtx_setParameter(cctx_, ZSTD_c_compressionLevel,
                             kZstdCompressionLevel);
      ZSTD_CCtx_setParameter(cctx_, ZSTD_c_contentSizeFlag, 1);
      ZSTD_CCtx_setParameter(cctx_, ZSTD_c_windowLog, 17);
    }
  }

  ~ZstdContext() {
    if (cctx_) ZSTD_freeCCtx(cctx_);
  }

  ZSTD_CCtx* get() const { return cctx_; }
  bool isValid() const { return cctx_ != nullptr; }

 private:
  ZSTD_CCtx* cctx_;
};

// This plugin compresses HTTP responses using zstd when the client
// supports it and the content type is compressible.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto accept_encoding = getRequestHeader("Accept-Encoding");
    if (accept_encoding) {
      client_supports_zstd_ = shouldUseZstd(accept_encoding->view());
    }
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    if (!client_supports_zstd_) {
      return FilterHeadersStatus::Continue;
    }

    // Do not re-encode if the response is already encoded.
    const auto existing_encoding = getResponseHeader("Content-Encoding");
    if (existing_encoding && !existing_encoding->view().empty()) {
      return FilterHeadersStatus::Continue;
    }

    const auto content_type = getResponseHeader("Content-Type");
    if (!content_type || !isCompressibleContentType(content_type->view())) {
      return FilterHeadersStatus::Continue;
    }

    const auto content_length_header = getResponseHeader("Content-Length");
    if (!content_length_header) {
      // No Content-Length means chunked transfer encoding.
      is_chunked_mode_ = true;
      should_compress_ = true;
      return FilterHeadersStatus::Continue;
    }

    size_t content_length = 0;
    if (!absl::SimpleAtoi(content_length_header->view(), &content_length) ||
        content_length == 0 || content_length > kMaxSizeBytes) {
      return FilterHeadersStatus::Continue;
    }

    original_content_length_ = content_length;
    should_compress_ = true;
    headers_modified_ = true;
    removeResponseHeader("Content-Length");
    addResponseHeader("Content-Encoding", "zstd");
    addResponseHeader("Vary", "Accept-Encoding");

    return FilterHeadersStatus::Continue;
  }

  FilterDataStatus onResponseBody(size_t body_buffer_length,
                                  bool end_of_stream) override {
    if (!should_compress_) {
      return FilterDataStatus::Continue;
    }

    // Buffer the response body so we can compress the full payload.
    const auto chunk =
        getBufferBytes(WasmBufferType::HttpResponseBody, 0, body_buffer_length);
    if (chunk) {
      body_buffer_.append(reinterpret_cast<const char*>(chunk->data()),
                          chunk->size());
    }

    // Abort compression for chunked responses if size exceeds limit.
    if (is_chunked_mode_ && body_buffer_.size() > kMaxSizeBytes) {
      return abortCompression();
    }

    if (!end_of_stream) {
      // Wait for the full response body.
      return FilterDataStatus::StopIterationAndBuffer;
    }

    if (body_buffer_.empty()) {
      return abortCompression();
    }

    if (!compressData(body_buffer_, compressed_buffer_)) {
      return abortCompression();
    }

    // Only use the compressed version if it is smaller.
    if (compressed_buffer_.size() >= body_buffer_.size()) {
      return abortCompression();
    }

    // For chunked responses, set Content-Encoding only if compression
    // is actually applied.
    if (is_chunked_mode_ && !headers_modified_) {
      addResponseHeader("Content-Encoding", "zstd");
      addResponseHeader("Vary", "Accept-Encoding");
      headers_modified_ = true;
    }

    setBuffer(WasmBufferType::HttpResponseBody, 0, body_buffer_.size(),
              compressed_buffer_);
    
    if (!is_chunked_mode_) {
      addResponseHeader("Content-Length",
                        std::to_string(compressed_buffer_.size()));
    }

    body_buffer_.clear();
    compressed_buffer_.clear();
    return FilterDataStatus::Continue;
  }

 private:
  // Abort compression and restore headers if they were modified.
  FilterDataStatus abortCompression() {
    should_compress_ = false;
    body_buffer_.clear();
    compressed_buffer_.clear();
    
    if (headers_modified_) {
      removeResponseHeader("Content-Encoding");
      removeResponseHeader("Vary");
      if (original_content_length_ > 0) {
        addResponseHeader("Content-Length",
                          std::to_string(original_content_length_));
      }
      headers_modified_ = false;
    }
    
    return FilterDataStatus::Continue;
  }

  // Decide whether zstd should be used based on Accept-Encoding q-values.
  bool shouldUseZstd(std::string_view accept_encoding) {
    float zstd_q = 0.0f;
    float best_other_q = 0.0f;

    for (auto encoding_part : absl::StrSplit(accept_encoding, ',')) {
      encoding_part = absl::StripAsciiWhitespace(encoding_part);
      if (encoding_part.empty()) continue;

      std::vector<std::string_view> parts = absl::StrSplit(encoding_part, ';');
      if (parts.empty()) continue;

      std::string_view encoding = absl::StripAsciiWhitespace(parts[0]);
      float q_value = 1.0f;

      for (size_t i = 1; i < parts.size(); i++) {
        auto param = absl::StripAsciiWhitespace(parts[i]);
        if (absl::StartsWith(param, "q=") || absl::StartsWith(param, "Q=")) {
          if (!absl::SimpleAtof(param.substr(2), &q_value)) {
            q_value = 1.0f;
          }
          q_value = std::max(0.0f, std::min(1.0f, q_value));
          break;
        }
      }

      if (encoding == "zstd") {
        zstd_q = q_value;
      } else if (encoding == "br" || encoding == "gzip" ||
                 encoding == "deflate") {
        best_other_q = std::max(best_other_q, q_value);
      }
    }

    return zstd_q > 0.0f && zstd_q >= best_other_q;
  }

  // Check if the content type is suitable for compression.
  static bool isCompressibleContentType(std::string_view ct) {
    return absl::StrContains(ct, "text/") ||
           absl::StrContains(ct, "application/json") ||
           absl::StrContains(ct, "application/javascript") ||
           absl::StrContains(ct, "application/xml") ||
           absl::StrContains(ct, "application/xhtml") ||
           absl::StrContains(ct, "+json") ||
           absl::StrContains(ct, "+xml") ||
           absl::StrContains(ct, "svg");
  }

  // Compress the given input using the zstd library.
  bool compressData(const std::string& input, std::string& output) {
    ZstdContext ctx;
    if (!ctx.isValid()) {
      return false;
    }

    const size_t max_compressed_size = ZSTD_compressBound(input.size());
    if (max_compressed_size == 0) {
      return false;
    }

    output.resize(max_compressed_size);

    const size_t compressed_size =
        ZSTD_compress2(ctx.get(), output.data(), output.size(), input.data(),
                       input.size());

    if (ZSTD_isError(compressed_size)) {
      return false;
    }

    output.resize(compressed_size);
    output.shrink_to_fit();
    return true;
  }

  bool client_supports_zstd_ = false;
  bool should_compress_ = false;
  bool is_chunked_mode_ = false;
  bool headers_modified_ = false;
  size_t original_content_length_ = 0;
  std::string body_buffer_;
  std::string compressed_buffer_;
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_zstd_compression]
