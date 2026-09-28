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

// [START serviceextensions_plugin_set_cookie]
#include "absl/random/random.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_split.h"
#include "proxy_wasm_intrinsics.h"

constexpr absl::string_view kCookieName = "my_cookie";
constexpr size_t kMaxCookieLength = 4096;
constexpr size_t kMaxSessionIdLength = 128;

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
    
    if (session_id_.has_value()) {
      LOG_DEBUG("Found existing session ID in request");
    } else {
      LOG_DEBUG("No valid session ID found in request");
    }

    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    if (session_id_.has_value()) {
      LOG_INFO("This current request is for the existing session ID: " + *session_id_);
    } else {
      const std::string new_session_id =
          std::to_string(root_->generateRandom());
      LOG_INFO("New session ID created for the current request: " +
               new_session_id);
      
      std::string cookie_value = absl::StrCat(
          kCookieName, "=", new_session_id, "; Path=/; HttpOnly");
      
      auto result = addResponseHeader("Set-Cookie", cookie_value);
      
      if (result == WasmResult::Ok) {
        LOG_DEBUG("Successfully added Set-Cookie header");
      } else {
        LOG_ERROR("Failed to add Set-Cookie header. Error code: " + 
                  std::to_string(static_cast<int>(result)));
      }
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  std::optional<std::string> session_id_;
  MyRootContext* root_;

  // Validate if the session ID has a valid format
  static bool isValidSessionId(const std::string& session_id) {
    // Session ID should not be empty
    if (session_id.empty()) {
      LOG_DEBUG("Empty session ID rejected");
      return false;
    }
    
    // Prevent excessively long session IDs
    if (session_id.length() > kMaxSessionIdLength) {
      LOG_DEBUG("Session ID too long: " + std::to_string(session_id.length()) + 
                " characters (max " + std::to_string(kMaxSessionIdLength) + ")");
      return false;
    }
    
    // Session ID should only contain valid characters (alphanumeric)
    for (char c : session_id) {
      if (!std::isalnum(c)) {
        LOG_DEBUG("Session ID contains invalid character: " + std::string(1, c));
        return false;
      }
    }
    
    return true;
  }

  // Try to get the session ID from the Cookie header.
  std::optional<std::string> getSessionIdFromCookie() {
    // Get the Cookie header
    auto cookie_header_ptr = getRequestHeader("Cookie");
    
    // Check if header exists by verifying the pointer and calling view()
    if (!cookie_header_ptr) {
      LOG_DEBUG("getRequestHeader returned null pointer");
      return std::nullopt;
    }
    
    // Get the string value
    std::string cookies = cookie_header_ptr->toString();
    
    // Check if cookie header is empty
    if (cookies.empty()) {
      LOG_DEBUG("Empty Cookie header found");
      return std::nullopt;
    }
    
    // Prevent excessively large cookie headers (potential DoS)
    if (cookies.length() > kMaxCookieLength) {
      LOG_WARN("Cookie header too large (" + std::to_string(cookies.length()) + 
               " bytes), ignoring for security");
      return std::nullopt;
    }
    
    LOG_DEBUG("Parsing Cookie header: " + cookies);
    
    // Split cookie header into individual cookie pairs
    for (absl::string_view sp : absl::StrSplit(cookies, "; ")) {
      if (sp.empty()) {
        LOG_DEBUG("Empty cookie pair found, skipping");
        continue;
      }
      
      // Split each cookie into name and value
      std::vector<std::string> parts = absl::StrSplit(sp, absl::MaxSplits('=', 1));
      
      // Check if cookie has both name and value
      if (parts.size() != 2) {
        LOG_DEBUG("Malformed cookie pair, skipping: " + std::string(sp));
        continue;
      }
      
      // Check if this is our cookie
      if (parts[0] == kCookieName) {
        LOG_DEBUG("Found target cookie: " + std::string(kCookieName));
        
        // Validate the session ID format
        if (isValidSessionId(parts[1])) {
          LOG_DEBUG("Valid session ID found: " + parts[1]);
          return parts[1];
        } else {
          LOG_WARN("Invalid session ID format for cookie " + std::string(kCookieName) +
                   ": " + parts[1]);
          return std::nullopt;
        }
      }
    }
    
    LOG_DEBUG("Cookie " + std::string(kCookieName) + " not found in request");
    return std::nullopt;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_set_cookie]
