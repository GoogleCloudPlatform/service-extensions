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

// [START serviceextensions_plugin_set_cookie]
#include "absl/random/random.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_split.h"
#include "proxy_wasm_intrinsics.h"

constexpr absl::string_view kCookieName = "my_cookie";

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  uint64_t generateRandom() { return absl::Uniform<uint64_t>(bitgen_); }

 private:
  absl::BitGen bitgen_;
};

// This plugin verifies if a session ID cookie is present in the current
// request. If no such cookie is found, a new session ID cookie is created.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<MyRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    session_id_ = getSessionIdFromCookie();

    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    if (session_id_.has_value()) {
      LOG_INFO("This current request is for the existing session ID: " +
               *session_id_);
    } else {
      const std::string new_session_id =
          std::to_string(root_->generateRandom());
      LOG_INFO("New session ID created for the current request: " +
               new_session_id);
      addResponseHeader(
          "Set-Cookie",
          absl::StrCat(kCookieName, "=", new_session_id, "; Path=/; HttpOnly"));
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  std::optional<std::string> session_id_;

  // Try to get the session ID from the Cookie header.
  static std::optional<std::string> getSessionIdFromCookie() {
    const auto cookies = getRequestHeader("Cookie")->toString();
    std::map<std::string, std::string> m;
    for (absl::string_view sp : absl::StrSplit(cookies, "; ")) {
      const std::pair<std::string, std::string> cookie =
          absl::StrSplit(sp, absl::MaxSplits('=', 1));
      if (cookie.first == kCookieName) {
        return cookie.second;
      }
    }

    return std::nullopt;
  }

  MyRootContext* root_;
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_set_cookie]
