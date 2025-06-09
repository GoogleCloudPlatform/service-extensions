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

// [START serviceextensions_plugin_hmac_token_validation]
#include <openssl/hmac.h>
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>

#include "absl/strings/escaping.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_split.h"
#include "absl/time/clock.h"
#include "proxy_wasm_intrinsics.h"

class HmacValidationRootContext : public RootContext {
public:
  explicit HmacValidationRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t) override {
    LOG_DEBUG("HMAC validation plugin configured");
    return true;
  }
  
  // Replace with your desired secret key.
  std::string secret_key_ = "your-secret-key";
  // Token validity period in seconds (5 minutes).
  const int64_t token_validity_seconds_ = 300;
};

// Validates incoming requests using HMAC authentication tokens.
// The token must be provided in the Authorization header with format:
// "HMAC timestamp:hmac_signature" where:
// - timestamp: Unix timestamp when token was created
// - hmac_signature: HMAC-MD5 signature of "METHOD:PATH:timestamp" using secret key
class HmacValidationContext : public Context {
public:
  explicit HmacValidationContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<HmacValidationRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers_size, bool end_of_stream) override {
    LOG_DEBUG(absl::StrCat("Processing request with ", headers_size, " headers"));

    // 1. Check if Authorization header exists
    auto auth_header = getRequestHeader("authorization");
    if (!auth_header || auth_header->view().empty()) {
      sendLocalResponse(401, 
                       "WWW-Authenticate: HMAC realm=\"api\"",
                       "Missing Authorization header", 
                       {});
      return FilterHeadersStatus::StopIteration;
    }

    // 2. Verify Authorization header format (must start with "HMAC ")
    std::string_view auth_value = auth_header->view();
    const std::string prefix = "HMAC ";
    
    if (auth_value.size() < prefix.size() || 
        !absl::EqualsIgnoreCase(auth_value.substr(0, prefix.size()), absl::string_view(prefix))) {
      sendLocalResponse(400, 
                       "", 
                       "Invalid Authorization scheme. Use 'HMAC'", 
                       {});
      return FilterHeadersStatus::StopIteration;
    }

    // 3. Parse token parts (timestamp:hmac)
    std::string token = std::string(auth_value.substr(prefix.size()));
    std::vector<std::string> token_parts = absl::StrSplit(token, absl::MaxSplits(':', 1)); 
    
    if (token_parts.size() != 2) {
      sendLocalResponse(400, "", "Invalid token format: expected 'timestamp:hmac'", {});
      return FilterHeadersStatus::StopIteration;
    }

    // 4. Validate timestamp format
    int64_t token_timestamp;
    if (!absl::SimpleAtoi(token_parts[0], &token_timestamp)) {
      sendLocalResponse(400, "", "Invalid timestamp", {});
      return FilterHeadersStatus::StopIteration;
    }

    // 5. Check if token is expired
    const uint64_t current_time = static_cast<uint64_t>(absl::ToUnixSeconds(absl::Now()));
    if ((current_time - token_timestamp) > root_->token_validity_seconds_) {
      sendLocalResponse(403, "", "Token expired", {});
      return FilterHeadersStatus::StopIteration;
    }

    // 6. Ensure required request headers are present
    auto path = getRequestHeader(":path");
    auto method = getRequestHeader(":method");
    if (!path || !method) {
      sendLocalResponse(400, "", "Missing required headers", {});
      return FilterHeadersStatus::StopIteration;
    }

    // 7. Calculate expected HMAC and compare with provided token
    std::string message = absl::StrCat(method->view(), path->view(), token_parts[0]);
    std::string expected_hmac = computeHmacMd5(message, root_->secret_key_);

    if (expected_hmac.empty()) {
      LOG_ERROR(absl::StrCat("Failed to compute HMAC for request path: ", path->view()));
      sendLocalResponse(500, "", "Internal server error during authentication", {});
      return FilterHeadersStatus::StopIteration;
    }

    LOG_DEBUG(absl::StrCat(
      "HMAC validation: method=", method->view(),
      ", path=", path->view(),
      ", timestamp=", token_parts[0],
      ", received=", token_parts[1],
      ", expected=", expected_hmac
    ));

    // 8. Reject request if HMAC signatures don't match
    if (expected_hmac != token_parts[1]) {
      auto remote_addr = getRequestHeader("x-forwarded-for");
      std::string client_ip = remote_addr ? std::string(remote_addr->view()) : "unknown";
      LOG_WARN(absl::StrCat("Invalid HMAC for request from ", client_ip));
      sendLocalResponse(403, "", "Invalid HMAC", {});
      return FilterHeadersStatus::StopIteration;
    }

    LOG_INFO(absl::StrCat("Successful authentication for path: ", path->view()));
    return FilterHeadersStatus::Continue;
  }

private:
  HmacValidationRootContext* root_;

  // Computes HMAC-MD5 signature of the given message using the provided key.
  // Returns the signature as a lowercase hex string or empty string on error.
  std::string computeHmacMd5(const std::string& message, const std::string& key) {
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;
    
    // Verify input parameters
    if (message.empty() || key.empty()) {
      LOG_ERROR("HMAC calculation failed: Empty message or key");
      return "";
    }
    
    // Calculate HMAC with return value checking
    unsigned char* hmac_result = HMAC(EVP_md5(), 
                                     key.data(), key.size(),
                                     reinterpret_cast<const unsigned char*>(message.data()), message.size(),
                                     hash, &hash_len);
    
    if (hmac_result == nullptr || hash_len == 0) {
      LOG_ERROR("OpenSSL HMAC calculation failed");
      return "";
    }
    
    LOG_DEBUG(absl::StrCat("Generated HMAC for message of length: ", message.size()));
    
    // Pre-allocate to avoid reallocations
    std::string result;
    result.reserve(hash_len * 2);
    
    // Use direct hex conversion for better performance
    static const char hex_chars[] = "0123456789abcdef";
    
    for (unsigned int i = 0; i < hash_len; i++) {
      result.push_back(hex_chars[(hash[i] >> 4) & 0xF]);
      result.push_back(hex_chars[hash[i] & 0xF]);
    }
    
    return result;
  }
};

static RegisterContextFactory register_HmacValidation(
    CONTEXT_FACTORY(HmacValidationContext),
    ROOT_FACTORY(HmacValidationRootContext));
// [END serviceextensions_plugin_hmac_token_validation]