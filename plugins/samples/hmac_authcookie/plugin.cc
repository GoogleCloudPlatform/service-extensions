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
#include "proxy_wasm_intrinsics.h"

// Replace with your desired secret key.
const std::string kSecretKey = "your_secret_key";

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const std::optional<std::string> token = getTokenFromCookie();
    if (!token.has_value()) {
      LOG_INFO("Access forbidden - missing HMAC cookie.");
      sendLocalResponse(403, "", "Access forbidden - missing HMAC cookie.\n",
                        {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    const std::string path = getRequestHeader(":path")->toString();
    if (computeHmacSignature(path) != token.value()) {
      LOG_INFO("Access forbidden - invalid HMAC cookie.");
      sendLocalResponse(403, "", "Access forbidden - invalid HMAC cookie.\n",
                        {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  // Try to get the HMAC auth token from the Cookie header.
  std::optional<std::string> getTokenFromCookie() {
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

  // Function to compute the HMAC signature.
  std::string computeHmacSignature(const std::string& data) {
    unsigned char* result;
    unsigned int len = EVP_MAX_MD_SIZE;

    result = HMAC(EVP_sha256(), kSecretKey.c_str(), kSecretKey.length(),
                  reinterpret_cast<const unsigned char*>(data.c_str()),
                  data.length(), nullptr, &len);
    return absl::BytesToHexString(reinterpret_cast<const char*>(result));
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_hmac_authcookie]