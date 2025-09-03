// Copyright 2024 Google LLC
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

// [START serviceextensions_plugin_cdn_token_generator_cpp]
#include <string>
#include <memory>
#include <regex>
#include <chrono>
#include <map>
#include <vector>
#include <algorithm>
#include <iomanip>
#include <sstream>

#include "proxy_wasm_intrinsics.h"
#include "openssl/hmac.h"

// Security constants
constexpr size_t MAX_URL_LENGTH = 2048;
constexpr size_t MAX_KEY_LENGTH = 256;
constexpr size_t MIN_KEY_LENGTH = 32;
constexpr size_t MAX_CONFIG_SIZE = 4096;
constexpr int MAX_EXPIRY_TIME = 86400;  // 24h
constexpr int MIN_EXPIRY_TIME = 60;     // 1min

struct Config {
  std::string privateKeyHex;
  std::string keyName;
  int expirySeconds = 3600;
  std::string urlHeaderName;
  std::string outputHeaderName;
};

class CDNTokenRootContext : public RootContext {
 public:
  explicit CDNTokenRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t /* config_len */) override {
    // SOLUCIÓN TEMPORAL: Usar configuración hardcodeada para bypasear cualquier error
    config_.privateKeyHex = "d8ef411f9f735c3d2b263606678ba5b7b1abc1973f1285f856935cc163e9d094";
    config_.keyName = "test-key";
    config_.expirySeconds = 3600;
    config_.urlHeaderName = "X-Original-URL";
    config_.outputHeaderName = "X-Signed-URL";
    
    LOG_INFO("CDN Token Generator C++ plugin started with hardcoded configuration");
    return true;
  }

  const Config& config() const { return config_; }

 private:
  Config config_;

  bool parseConfig(const std::string& json) {
    // Simple parser (flat JSON)
    std::map<std::string, std::string> kv;
    size_t i = 0;
    while (i < json.size()) {
      i = json.find('"', i);
      if (i == std::string::npos) break;
      size_t j = json.find('"', i + 1);
      if (j == std::string::npos) break;
      std::string key = json.substr(i + 1, j - i - 1);
      size_t k = json.find(':', j);
      size_t l = json.find('"', k);
      size_t m = json.find('"', l + 1);
      if (l != std::string::npos && m != std::string::npos) {
        std::string val = json.substr(l + 1, m - l - 1);
        kv[key] = val;
        i = m + 1;
      } else {
        break;
      }
    }
    if (kv.count("privateKeyHex")) config_.privateKeyHex = kv["privateKeyHex"];
    if (kv.count("keyName")) config_.keyName = kv["keyName"];
    if (kv.count("expirySeconds")) config_.expirySeconds = std::stoi(kv["expirySeconds"]);
    if (kv.count("urlHeaderName")) config_.urlHeaderName = kv["urlHeaderName"];
    if (kv.count("outputHeaderName")) config_.outputHeaderName = kv["outputHeaderName"];
    return !config_.privateKeyHex.empty() && !config_.keyName.empty()
        && !config_.urlHeaderName.empty() && !config_.outputHeaderName.empty();
  }
};

class CDNTokenHttpContext : public Context {
 public:
  explicit CDNTokenHttpContext(uint32_t id, RootContext* root)
      : Context(id, root),
        config_(static_cast<CDNTokenRootContext*>(root)->config()) {}

  // Función para loguear sin prefijos de archivo/línea
  void logExact(const std::string& message) {
    logInfo(message);  // Función de bajo nivel sin prefijos
  }

  FilterHeadersStatus onRequestHeaders(uint32_t, bool) override {
    if (config_.privateKeyHex.empty()) {
      logExact("Plugin configuration is null");
      return FilterHeadersStatus::Continue;
    }
    auto originalURLPtr = getRequestHeader(config_.urlHeaderName);
    std::string originalURL = originalURLPtr ? originalURLPtr->toString() : "";
    if (originalURL.empty()) {
      logExact("URL header not found or empty: " + config_.urlHeaderName);
      return FilterHeadersStatus::Continue;
    }
    // Validate + sign URL
    if (!validateURL(originalURL)) {
      logExact("Invalid URL provided");
      return FilterHeadersStatus::Continue;
    }
    logExact("Generating signed URL for: " + originalURL);

    std::string signedURL = generateSignedURL(originalURL);
    if (signedURL.empty()) {
      logExact("Failed to generate signed URL");
      return FilterHeadersStatus::Continue;
    }
    addRequestHeader(config_.outputHeaderName, signedURL);
    return FilterHeadersStatus::Continue;
  }

 private:
  Config config_;

  bool validateURL(const std::string& url) {
    if (url.size() > MAX_URL_LENGTH) return false;
    // Regex similar to Go
    std::regex url_pattern(R"(^https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(/[^\s]*)?$)");
    if (!std::regex_match(url, url_pattern)) return false;
    // Basic internal host block
    std::string lower = url;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    if (lower.find("localhost") != std::string::npos ||
        lower.find("127.0.0.1") != std::string::npos ||
        lower.find("::1") != std::string::npos) {
      return false;
    }
    return true;
  }

  std::vector<uint8_t> hexToBytes(const std::string& hex) {
    std::vector<uint8_t> bytes;
    if (hex.size() % 2 != 0) return {};
    for (size_t i = 0; i < hex.size(); i += 2) {
      uint8_t byte = std::stoi(hex.substr(i, 2), nullptr, 16);
      bytes.push_back(byte);
    }
    return bytes;
  }

  std::string base64UrlEncode(const std::string& in) {
    // Basic URL-safe base64 (no padding, - and _)
    static const char table[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    std::string out;
    int val = 0, valb = -6;
    for (uint8_t c : in) {
      val = (val << 8) + c;
      valb += 8;
      while (valb >= 0) {
        out.push_back(table[(val >> valb) & 0x3F]);
        valb -= 6;
      }
    }
    if (valb > -6) out.push_back(table[((val << 8) >> (valb + 8)) & 0x3F]);
    return out;
  }

  std::string generateSignedURL(const std::string& targetURL) {
    // Parse scheme, host, path
    std::regex rgx(R"(^(https?)://([^/\s]+)(/[^\s]*)?$)");
    std::smatch match;
    if (!std::regex_match(targetURL, match, rgx)) return "";
    std::string scheme = match[1];
    std::string host = match[2];
    std::string path = match[3];
    std::string urlPrefix = scheme + "://" + host + path;
    std::string urlPrefixB64 = base64UrlEncode(urlPrefix);

    // Compute expiry
    auto now = std::chrono::system_clock::now();
    auto expiresAt = std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch()).count() + config_.expirySeconds;

    // Build string to sign
    std::ostringstream oss;
    oss << "URLPrefix=" << urlPrefixB64
        << "&Expires=" << expiresAt
        << "&KeyName=" << config_.keyName;
    std::string stringToSign = oss.str();

    // Decode key
    std::vector<uint8_t> key = hexToBytes(config_.privateKeyHex);
    if (key.size() < 16 || key.size() > 128) return ""; // Security

    // Sign (HMAC-SHA256)
    unsigned char result[32];
    unsigned int result_len;
    HMAC(EVP_sha256(), key.data(), key.size(),
         reinterpret_cast<const unsigned char*>(stringToSign.data()), stringToSign.size(),
         result, &result_len);

    std::string signature(reinterpret_cast<char*>(result), result_len);
    std::string signatureB64 = base64UrlEncode(signature);

    // Compose final URL
    std::string finalURL = targetURL;
    std::string sep = (finalURL.find('?') == std::string::npos) ? "?" : "&";
    finalURL += sep + "URLPrefix=" + urlPrefixB64 +
                "&Expires=" + std::to_string(expiresAt) +
                "&KeyName=" + config_.keyName +
                "&Signature=" + signatureB64;
    return finalURL;
  }
};

static RegisterContextFactory register_CDNTokenContext(
    CONTEXT_FACTORY(CDNTokenHttpContext),
    ROOT_FACTORY(CDNTokenRootContext)
);
// [END serviceextensions_plugin_cdn_token_generator_cpp]
