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

// [START serviceextensions_plugin_jwt_auth]
#include <boost/url/parse.hpp>
#include <boost/url/url.hpp>

#include "jwt_verify_lib/verify.h"
#include "proxy_wasm_intrinsics.h"

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t config_len) override {
    // Fetch plugin config and take ownership of the buffer.
    config_ =
        getBufferBytes(WasmBufferType::PluginConfiguration, 0, config_len);

    // Read the RSA key from the config file.
    const std::string rsa_key = config_->toString();
    jwks_ = google::jwt_verify::Jwks::createFrom(
        rsa_key, google::jwt_verify::Jwks::Type::PEM);
    return jwks_->getStatus() == google::jwt_verify::Status::Ok;
  }

  const google::jwt_verify::JwksPtr& jwks() const { return jwks_; }

 private:
  WasmDataPtr config_;
  google::jwt_verify::JwksPtr jwks_;
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<MyRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto path = getRequestHeader(":path");
    if (path && path->size() > 0) {
      boost::system::result<boost::urls::url> url =
          boost::urls::parse_uri_reference(path->view());
      auto it = url->params().find("jwt");
      // Check if the JWT token exists.
      if (it == url->params().end()) {
        LOG_INFO("Access forbidden - missing token.");
        sendLocalResponse(403, "", "Access forbidden - missing token.\n", {});
        return FilterHeadersStatus::ContinueAndEndStream;
      }

      google::jwt_verify::Jwt jwt;
      // Check if the JWT token is valid.
      if (jwt.parseFromString((*it).value) != google::jwt_verify::Status::Ok) {
        LOG_INFO("Access forbidden - invalid token.");
        sendLocalResponse(403, "", "Access forbidden - invalid token.\n", {});
        return FilterHeadersStatus::ContinueAndEndStream;
      }

      // Check if the JWT is allowed.
      const auto status = google::jwt_verify::verifyJwt(jwt, *root_->jwks());
      if (status != google::jwt_verify::Status::Ok) {
        LOG_INFO("Access forbidden.");
        sendLocalResponse(403, "", "Access forbidden.\n", {});
        return FilterHeadersStatus::ContinueAndEndStream;
      }

      // Strip the JWT from the URL after validation.
      url->params().erase(it);
      replaceRequestHeader(":path", url->buffer());
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  const MyRootContext* root_;
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_jwt_auth]
