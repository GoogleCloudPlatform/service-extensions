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

// [START serviceextensions_plugin_set__reset_cookie]
#include "absl/strings/str_cat.h"
#include "absl/strings/str_split.h"
#include "absl/strings/match.h"
#include "absl/strings/strip.h"
#include "proxy_wasm_intrinsics.h"
#include <map>
#include <vector>

// Cookie operation types
enum class CookieOperation {
  SET,      // Set or reset a cookie value
  DELETE,   // Delete a cookie before CDN cache
  OVERWRITE // Overwrite existing cookies
};

// Cookie configuration based on Apache log format
struct CookieConfig {
  std::string name;
  std::string value;
  std::string domain;
  std::string path;
  int max_age;  // -1 for session cookie, >0 for persistent
  bool secure;
  bool http_only;
  bool same_site_strict;
  CookieOperation operation;

  CookieConfig()
      : path("/"),
        max_age(-1),
        secure(false),
        http_only(true),
        same_site_strict(false),
        operation(CookieOperation::SET) {}
};

class CookieManagerRootContext : public RootContext {
 public:
  explicit CookieManagerRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t config_size) override {
    auto configuration_data = getBufferBytes(WasmBufferType::PluginConfiguration,
                                            0, config_size);
    parseConfiguration(configuration_data->view());
    return true;
  }

  const std::vector<CookieConfig>& getCookieConfigs() const {
    return cookie_configs_;
  }

 private:
  std::vector<CookieConfig> cookie_configs_;

  // Parse configuration in Apache log format style
  // Format: "cookie_name=value; Domain=example.com; Path=/; Max-Age=3600; Secure; HttpOnly"
  void parseConfiguration(std::string_view config) {
    for (absl::string_view line : absl::StrSplit(config, '\n')) {
      line = absl::StripAsciiWhitespace(line);
      if (line.empty() || absl::StartsWith(line, "#")) {
        continue;
      }

      CookieConfig cookie_config;
      
      // Parse each directive separated by semicolons
      std::vector<std::string> directives = absl::StrSplit(line, "; ");
      
      for (size_t i = 0; i < directives.size(); ++i) {
        std::string directive = directives[i];
        
        if (i == 0) {
          // First directive is the cookie name=value or operation
          if (absl::StartsWith(directive, "DELETE:")) {
            cookie_config.operation = CookieOperation::DELETE;
            cookie_config.name = directive.substr(7);
          } else if (absl::StartsWith(directive, "OVERWRITE:")) {
            cookie_config.operation = CookieOperation::OVERWRITE;
            auto name_value = absl::StrSplit(directive.substr(10), '=');
            auto parts = std::vector<std::string>(name_value.begin(), name_value.end());
            if (parts.size() >= 2) {
              cookie_config.name = parts[0];
              cookie_config.value = parts[1];
            }
          } else {
            cookie_config.operation = CookieOperation::SET;
            auto name_value = absl::StrSplit(directive, '=');
            auto parts = std::vector<std::string>(name_value.begin(), name_value.end());
            if (parts.size() >= 2) {
              cookie_config.name = parts[0];
              cookie_config.value = parts[1];
            }
          }
        } else {
          // Parse cookie attributes
          if (absl::StartsWith(directive, "Domain=")) {
            cookie_config.domain = directive.substr(7);
          } else if (absl::StartsWith(directive, "Path=")) {
            cookie_config.path = directive.substr(5);
          } else if (absl::StartsWith(directive, "Max-Age=")) {
            cookie_config.max_age = std::stoi(directive.substr(8));
          } else if (directive == "Secure") {
            cookie_config.secure = true;
          } else if (directive == "HttpOnly") {
            cookie_config.http_only = true;
          } else if (directive == "SameSite=Strict") {
            cookie_config.same_site_strict = true;
          } else if (directive == "Session") {
            cookie_config.max_age = -1;
          }
        }
      }
      
      cookie_configs_.push_back(cookie_config);
    }
  }
};

// Main HTTP context for cookie management
class CookieManagerHttpContext : public Context {
 public:
  explicit CookieManagerHttpContext(uint32_t id, RootContext* root)
      : Context(id, root),
        root_(static_cast<CookieManagerRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Parse existing cookies from request
    parseRequestCookies();
    
    // Process DELETE operations before CDN cache
    processCookieDeletions();
    
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    // Process SET and OVERWRITE operations
    processCookieOperations();
    
    return FilterHeadersStatus::Continue;
  }

 private:
  CookieManagerRootContext* root_;
  std::map<std::string, std::string> request_cookies_;
  std::vector<std::string> cookies_to_delete_;

  // Parse cookies from the Cookie header
  void parseRequestCookies() {
    auto cookie_header = getRequestHeader("Cookie");
    if (!cookie_header) {
      return;
    }

    const std::string cookies = cookie_header->toString();
    for (absl::string_view cookie_pair : absl::StrSplit(cookies, "; ")) {
      std::vector<std::string> parts = absl::StrSplit(cookie_pair, absl::MaxSplits('=', 1));
      if (parts.size() == 2) {
        request_cookies_[parts[0]] = parts[1];
      }
    }
  }

  // Process cookie deletions before CDN cache
  void processCookieDeletions() {
    const auto& configs = root_->getCookieConfigs();
    
    for (const auto& config : configs) {
      if (config.operation == CookieOperation::DELETE) {
        if (request_cookies_.find(config.name) != request_cookies_.end()) {
          cookies_to_delete_.push_back(config.name);
          LOG_INFO("Marking cookie for deletion before CDN cache: " + config.name);
        }
      }
    }
    
    // Remove deleted cookies from request
    if (!cookies_to_delete_.empty()) {
      rebuildCookieHeader();
    }
  }

  // Rebuild Cookie header without deleted cookies
  void rebuildCookieHeader() {
    std::vector<std::string> remaining_cookies;
    
    for (const auto& cookie : request_cookies_) {
      bool should_delete = false;
      for (const auto& name : cookies_to_delete_) {
        if (cookie.first == name) {
          should_delete = true;
          break;
        }
      }
      
      if (!should_delete) {
        remaining_cookies.push_back(absl::StrCat(cookie.first, "=", cookie.second));
      }
    }
    
    if (remaining_cookies.empty()) {
      removeRequestHeader("Cookie");
    } else {
      replaceRequestHeader("Cookie", absl::StrJoin(remaining_cookies, "; "));
    }
  }

  // Process SET and OVERWRITE operations
  void processCookieOperations() {
    const auto& configs = root_->getCookieConfigs();
    
    for (const auto& config : configs) {
      if (config.operation == CookieOperation::SET) {
        setCookie(config);
      } else if (config.operation == CookieOperation::OVERWRITE) {
        overwriteCookie(config);
      }
    }
  }

  // Set or reset a cookie
  void setCookie(const CookieConfig& config) {
    std::string cookie_value = absl::StrCat(config.name, "=", config.value);
    
    // Add Path attribute
    absl::StrAppend(&cookie_value, "; Path=", config.path);
    
    // Add Domain attribute if specified
    if (!config.domain.empty()) {
      absl::StrAppend(&cookie_value, "; Domain=", config.domain);
    }
    
    // Add Max-Age for persistent cookies (session if -1)
    if (config.max_age > 0) {
      absl::StrAppend(&cookie_value, "; Max-Age=", config.max_age);
    }
    
    // Add security attributes
    if (config.http_only) {
      absl::StrAppend(&cookie_value, "; HttpOnly");
    }
    
    if (config.secure) {
      absl::StrAppend(&cookie_value, "; Secure");
    }
    
    if (config.same_site_strict) {
      absl::StrAppend(&cookie_value, "; SameSite=Strict");
    }
    
    addResponseHeader("Set-Cookie", cookie_value);
    
    std::string log_type = (config.max_age == -1) ? "session" : "persistent";
    LOG_INFO("Setting " + log_type + " cookie: " + config.name + "=" + config.value);
  }

  // Overwrite or remove existing Set-Cookie headers
  void overwriteCookie(const CookieConfig& config) {
    // Remove all existing Set-Cookie headers for this cookie
    removeResponseHeader("Set-Cookie");
    
    // If value is not empty, set the new cookie
    if (!config.value.empty()) {
      setCookie(config);
      LOG_INFO("Overwriting existing cookie: " + config.name);
    } else {
      // Complete removal - set expired cookie
      std::string expire_cookie = absl::StrCat(
          config.name, "=; Path=", config.path, "; Max-Age=0");
      
      if (!config.domain.empty()) {
        absl::StrAppend(&expire_cookie, "; Domain=", config.domain);
      }
      
      addResponseHeader("Set-Cookie", expire_cookie);
      LOG_INFO("Removing Set-Cookie directive for: " + config.name);
    }
  }
};

static RegisterContextFactory register_CookieManagerContext(
    CONTEXT_FACTORY(CookieManagerHttpContext),
    ROOT_FACTORY(CookieManagerRootContext));
// [END serviceextensions_plugin_set_reset_cookie]
