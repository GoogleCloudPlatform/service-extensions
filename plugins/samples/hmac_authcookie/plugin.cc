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

// [START serviceextensions_plugin_hmac_authcookie]
#include <openssl/hmac.h>

#include <string>

#include "absl/strings/escaping.h"
#include "absl/strings/str_split.h"
#include "absl/time/clock.h"
#include "absl/time/time.h"
#include "proxy_wasm_intrinsics.h"
#include "re2/re2.h"

// Replace with your desired secret key.
const std::string kSecretKey = "your_secret_key";

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t) override {
    // Regex for matching IPs on format like 127.0.0.1.
    ip_match.emplace("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$");
    return ip_match->ok();
  }

  std::optional<re2::RE2> ip_match;
};

// Validates the HMAC HTTP cookie performing the following steps:
//
// 1. Obtains the client IP address and rejects the request if it is not
// present.
// 2. Obtains the HTTP cookie and rejects the request if it is not present.
// 3. Verifies that the HMAC hash of the cookie matches its payload, rejecting
// the request if there is no match.
// 4. Ensures that the client IP address matches the IP in the cookie payload,
// and that the current time is earlier than the expiration time specified in
// the cookie payload.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<MyRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const std::optional<std::string> ip = getClientIp();
    if (!ip.has_value()) {
      LOG_INFO("Access forbidden - missing client IP.");
      sendLocalResponse(403, "", "Access forbidden - missing client IP.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    const std::optional<std::string> token = getAuthorizationCookie();
    if (!token.has_value()) {
      LOG_INFO("Access forbidden - missing HMAC cookie.");
      sendLocalResponse(403, "", "Access forbidden - missing HMAC cookie.\n",
                        {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    const std::optional<std::pair<std::string, std::string>> payload_and_hash =
        parseAuthorizationCookie(token.value());
    if (!payload_and_hash.has_value()) {
      LOG_INFO("Access forbidden - invalid HMAC cookie.");
      sendLocalResponse(403, "", "Access forbidden - invalid HMAC cookie.\n",
                        {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    if (computeHmacSignature(payload_and_hash->first) !=
        payload_and_hash->second) {
      LOG_INFO("Access forbidden - invalid HMAC hash.");
      sendLocalResponse(403, "", "Access forbidden - invalid HMAC hash.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    const std::pair<std::string, std::string>
        client_ip_and_expiration_timestamp =
            absl::StrSplit(payload_and_hash->first, ',');
    if (ip != client_ip_and_expiration_timestamp.first) {
      LOG_INFO("Access forbidden - invalid client IP.");
      sendLocalResponse(403, "", "Access forbidden - invalid client IP.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    if (!isHashTimestampValid(client_ip_and_expiration_timestamp.second)) {
      LOG_INFO("Access forbidden - hash expired.");
      sendLocalResponse(403, "", "Access forbidden - hash expired.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  const MyRootContext* root_;

  // Check if the current time is earlier than cookie payload expiration.
  bool isHashTimestampValid(std::string_view expiration_timestamp) {
    const int64_t unix_now = absl::ToUnixNanos(absl::Now());
    int64_t parsed_expiration_timestamp;
    return absl::SimpleAtoi(expiration_timestamp,
                            &parsed_expiration_timestamp) &&
           unix_now <= parsed_expiration_timestamp;
  }

  // Try to get the client IP from the X-Forwarded-For header.
  std::optional<std::string> getClientIp() {
    const std::string ips = getRequestHeader("X-Forwarded-For")->toString();
    for (absl::string_view ip : absl::StrSplit(ips, ',')) {
      if (re2::RE2::FullMatch(ip, *root_->ip_match)) {
        return std::string(ip);
      }
    }

    return std::nullopt;
  }

  // Try to get the HMAC auth token from the Cookie header.
  std::optional<std::string> getAuthorizationCookie() {
    const std::string cookies = getRequestHeader("Cookie")->toString();
    std::map<std::string, std::string> m;
    for (absl::string_view sp : absl::StrSplit(cookies, "; ")) {
      const std::pair<std::string, std::string> cookie =
          absl::StrSplit(sp, absl::MaxSplits('=', 1));
      if (cookie.first == "Authorization") {
        return cookie.second;
      }
    }

    return std::nullopt;
  }

  // Try to parse the authorization cookie in the format
  // "base64(payload)" + "." + "base64(HMAC(payload))".
  std::optional<std::pair<std::string, std::string>> parseAuthorizationCookie(
      std::string_view cookie) {
    std::pair<std::string_view, std::string_view> payload_and_hash =
        absl::StrSplit(cookie, ".");
    std::string payload;
    std::string hash;
    if (!payload_and_hash.second.empty() &&
        absl::Base64Unescape(payload_and_hash.first, &payload) &&
        absl::Base64Unescape(payload_and_hash.second, &hash)) {
      return std::pair{payload, hash};
    }
    return std::nullopt;
  }

  // Function to compute the HMAC signature.
  std::string computeHmacSignature(std::string_view data) {
    unsigned char result[EVP_MAX_MD_SIZE];
    unsigned int len;
    HMAC(EVP_sha256(), kSecretKey.c_str(), kSecretKey.length(),
         reinterpret_cast<const unsigned char*>(std::string{data}.c_str()),
         data.length(), result, &len);
    return absl::BytesToHexString(std::string(result, result + len));
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_hmac_authcookie]