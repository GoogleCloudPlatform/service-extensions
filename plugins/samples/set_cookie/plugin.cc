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
#include "absl/strings/numbers.h"
#include "absl/strings/str_split.h"
#include "proxy_wasm_intrinsics.h"

// This plugin verifies if a session ID cookie is present in the current
// request. If no such cookie is found, a new session ID cookie is created.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

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
      const std::string new_session_id = generateSessionId();
      LOG_INFO("New session ID created for the current request: " +
               new_session_id);
      addResponseHeader("Set-Cookie",
                        "my_cookie=" + new_session_id + "; Path=/; HttpOnly");
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
      if (cookie.first == "my_cookie") {
        return cookie.second;
      }
    }

    return std::nullopt;
  }

  // Generate a unique random session ID.
  static std::string generateSessionId() {
    // Wasm VM does not support the random generation
    // that involves a file system operation.
    using namespace std::chrono_literals;
    const auto ts = std::chrono::high_resolution_clock::now();
    const auto ns = ts.time_since_epoch() / 1ns;
    return std::to_string(ns);
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_set_cookie]
