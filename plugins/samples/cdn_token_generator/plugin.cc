// Copyright 2026 Google LLC
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

// [START serviceextensions_plugin_cdn_token_generator]
//
// This plugin signs URLs embedded in response bodies (e.g., HLS/DASH manifests)
// with HMAC-SHA256 tokens for Google Cloud Media CDN authentication.
//
// Use case: A video streaming service returns a manifest file (.m3u8 or .mpd)
// from the origin containing segment URLs. This plugin intercepts the response,
// finds all HTTP/HTTPS URLs, and replaces them with signed URLs that include
// authentication tokens. This allows Media CDN to verify that requests for
// video segments come from authorized clients.

#include <openssl/hmac.h>
#include <google/protobuf/text_format.h>

#include <chrono>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "absl/strings/escaping.h"
#include "absl/strings/numbers.h"
#include "absl/strings/str_cat.h"
#include "proxy_wasm_intrinsics.h"
#include "re2/re2.h"

// Include the generated protobuf header
#include "samples/cdn_token_generator/cdn_token_config.pb.h"

using serviceextensions::cdn_token::CdnTokenConfig;

namespace {
// Security and operational limits.
constexpr size_t kMaxKeyHexLength = 256;
constexpr size_t kMinKeyHexLength = 32;
constexpr int kMaxExpirySeconds = 86400;   // 24 hours
constexpr int kMinExpirySeconds = 60;      // 1 minute
constexpr int kDefaultExpirySeconds = 3600;
// Maximum response body size to process (1MB). Larger bodies are passed through
// unmodified to prevent excessive memory usage and processing time.
constexpr size_t kMaxBodySize = 1024 * 1024;
}  // namespace

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t config_size) override {
    if (config_size == 0) {
      LOG_ERROR("Configuration is required");
      return false;
    }

    auto config_data =
        getBufferBytes(WasmBufferType::PluginConfiguration, 0, config_size);
    if (!config_data) {
      LOG_ERROR("Failed to read plugin configuration");
      return false;
    }

    if (!parseConfig(config_data->toString())) {
      return false;
    }

    url_pattern_ = std::make_unique<re2::RE2>("(https?://[^\\s\"'<>]+)");
    if (!url_pattern_->ok()) {
      LOG_ERROR(absl::StrCat("Failed to compile URL regex: ",
                             url_pattern_->error()));
      return false;
    }

    LOG_INFO(absl::StrCat("CDN Token Generator configured: keyName=",
                          config_->key_name(),
                          ", expirySeconds=", config_->expiry_seconds()));
    return true;
  }

  const CdnTokenConfig& config() const { return *config_; }
  const std::string& decoded_key() const { return decoded_key_; }
  const re2::RE2& url_pattern() const { return *url_pattern_; }

 private:
  // Using smart pointers ensures implicit destructors are safely marked noexcept,
  // matching the RootContext base class and preventing compiler errors.
  std::unique_ptr<CdnTokenConfig> config_;
  std::string decoded_key_;
  std::unique_ptr<re2::RE2> url_pattern_;

  bool parseConfig(const std::string& config_str) {
    config_ = std::make_unique<CdnTokenConfig>();
    
    if (!google::protobuf::TextFormat::ParseFromString(config_str, config_.get())) {
      LOG_ERROR("Failed to parse configuration as TextProto");
      return false;
    }

    // Apply defaults if not set
    if (config_->expiry_seconds() == 0) {
      config_->set_expiry_seconds(kDefaultExpirySeconds);
    }

    // Validation
    if (config_->private_key_hex().empty()) {
      LOG_ERROR("private_key_hex is required in configuration");
      return false;
    }
    if (config_->key_name().empty()) {
      LOG_ERROR("key_name is required in configuration");
      return false;
    }
    if (config_->private_key_hex().length() < kMinKeyHexLength ||
        config_->private_key_hex().length() > kMaxKeyHexLength) {
      LOG_ERROR(absl::StrCat("private_key_hex length must be between ",
                             kMinKeyHexLength, " and ", kMaxKeyHexLength));
      return false;
    }
    if (config_->expiry_seconds() < kMinExpirySeconds || 
        config_->expiry_seconds() > kMaxExpirySeconds) {
      LOG_ERROR(absl::StrCat("expiry_seconds must be between ",
                             kMinExpirySeconds, " and ", kMaxExpirySeconds));
      return false;
    }

    // Decode hex key once during configuration to save CPU cycles on every request
    if (!absl::HexStringToBytes(config_->private_key_hex(), &decoded_key_)) {
      LOG_ERROR("Failed to decode private key from hex");
      return false;
    }

    return true;
  }
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<MyRootContext*>(root)) {}

  FilterDataStatus onResponseBody(size_t body_buffer_length,
                                  bool end_of_stream) override {
    // Buffer the response until we have the complete body.
    if (!end_of_stream) {
      return FilterDataStatus::StopIterationAndBuffer;
    }

    // Skip processing for very large bodies to prevent OOM.
    if (body_buffer_length > kMaxBodySize) {
      LOG_WARN(absl::StrCat("Response body too large (", body_buffer_length,
                            " bytes), skipping URL signing"));
      return FilterDataStatus::Continue;
    }

    auto body =
        getBufferBytes(WasmBufferType::HttpResponseBody, 0, body_buffer_length);
    if (!body) {
      LOG_ERROR("Failed to read response body");
      return FilterDataStatus::Continue;
    }

    std::string body_string = body->toString();
    if (body_string.empty()) {
      return FilterDataStatus::Continue;
    }

    // Find all URL matches and their positions.
    std::vector<std::pair<size_t, std::string>> matches;
    re2::StringPiece input(body_string);
    re2::StringPiece match;

    while (RE2::FindAndConsume(&input, root_->url_pattern(), &match)) {
      size_t pos = match.data() - body_string.data();
      matches.emplace_back(pos, std::string(match));
    }

    if (matches.empty()) {
      return FilterDataStatus::Continue;
    }

    // Replace URLs from end to start to preserve positional indices.
    std::string modified_body = body_string;
    int replacements = 0;

    for (auto it = matches.rbegin(); it != matches.rend(); ++it) {
      const auto& [pos, url] = *it;
      std::string signed_url = generateSignedUrl(url);
      if (!signed_url.empty()) {
        modified_body.replace(pos, url.length(), signed_url);
        ++replacements;
      }
    }

    if (replacements > 0) {
      LOG_INFO(
          absl::StrCat("Replaced ", replacements, " URLs with signed URLs"));
      setBuffer(WasmBufferType::HttpResponseBody, 0, body_buffer_length,
                modified_body);
    }

    return FilterDataStatus::Continue;
  }

 private:
  const MyRootContext* root_;

  // Generates a signed URL in Media CDN token format.
  // See: https://cloud.google.com/media-cdn/docs/generate-tokens
  std::string generateSignedUrl(const std::string& target_url) {
    const auto& config = root_->config();

    // Base64 URL-safe encode the URL prefix.
    std::string url_prefix_b64 = base64UrlEncode(target_url);

    // Calculate expiration timestamp.
    auto now = std::chrono::system_clock::now();
    auto expires_at =
        std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch())
            .count() +
        config.expiry_seconds();

    // Create the string to sign (Media CDN token format).
    // Format: URLPrefix=<base64>~Expires=<timestamp>~KeyName=<key-name>
    std::string string_to_sign =
        absl::StrCat("URLPrefix=", url_prefix_b64, "~Expires=", expires_at,
                     "~KeyName=", config.key_name());

    // Compute HMAC-SHA256 signature using the pre-decoded key from RootContext.
    unsigned char hmac_result[EVP_MAX_MD_SIZE];
    unsigned int hmac_len;
    HMAC(EVP_sha256(),
         reinterpret_cast<const unsigned char*>(root_->decoded_key().data()),
         root_->decoded_key().size(),
         reinterpret_cast<const unsigned char*>(string_to_sign.data()),
         string_to_sign.size(), hmac_result, &hmac_len);

    // Convert HMAC to hexadecimal string (Media CDN uses hex, not base64).
    std::string hmac_hex = absl::BytesToHexString(
        std::string_view(reinterpret_cast<char*>(hmac_result), hmac_len));

    // Build final signed URL with Edge-Cache-Token parameter.
    // Format: <url>?Edge-Cache-Token=URLPrefix=<b64>~Expires=<ts>~KeyName=<n>~hmac=<hex>
    std::string_view separator =
        (target_url.find('?') == std::string::npos) ? "?" : "&";
    return absl::StrCat(target_url, separator,
                        "Edge-Cache-Token=", string_to_sign,
                        "~hmac=", hmac_hex);
  }

  // URL-safe Base64 encoding without padding.
  static std::string base64UrlEncode(const std::string& input) {
    std::string encoded;
    absl::WebSafeBase64Escape(input, &encoded);
    // Remove padding ('=' characters).
    size_t padding_pos = encoded.find('=');
    if (padding_pos != std::string::npos) {
      encoded.resize(padding_pos);
    }
    return encoded;
  }
};

static RegisterContextFactory register_MyHttpContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_cdn_token_generator]
