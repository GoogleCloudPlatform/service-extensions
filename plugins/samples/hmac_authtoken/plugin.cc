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

// [START serviceextensions_plugin_hmac_authtoken]
#include <openssl/hmac.h>

#include <boost/url/parse.hpp>
#include <boost/url/url.hpp>
#include <string>

#include "absl/strings/escaping.h"
#include "proxy_wasm_intrinsics.h"

// Replace with your desired secret key.
const std::string kSecretKey = "your_secret_key";

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    boost::system::result<boost::urls::url> url =
        boost::urls::parse_relative_ref(getRequestHeader(":path")->toString());

    if (!url) {
      LOG_ERROR("Error parsing the :path HTTP header: " +
                url.error().message());
      sendLocalResponse(400, "", "Error parsing the :path HTTP header.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    auto it = url->params().find("token");
    // Check if the HMAC token exists.
    if (it == url->params().end()) {
      LOG_INFO("Access forbidden - missing token.");
      sendLocalResponse(403, "", "Access forbidden - missing token.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    const std::string token = (*it).value;
    // Strip the token from the URL.
    url->params().erase(it);
    const std::string path = url->buffer();
    // Compare if the generated signature matches the token sent.
    // In this sample the signature is generated using the request :path.
    if (computeHmacSignature(path) != token) {
      LOG_INFO("Access forbidden - invalid token.");
      sendLocalResponse(403, "", "Access forbidden - invalid token.\n", {});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    replaceRequestHeader(":path", path);
    return FilterHeadersStatus::Continue;
  }

 private:
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
// [END serviceextensions_plugin_hmac_authtoken]
