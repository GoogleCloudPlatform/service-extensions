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

// [START serviceextensions_plugin_set_reset_cookie]
#include "absl/strings/ascii.h"
#include "absl/strings/match.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_join.h"
#include "absl/strings/str_split.h"
#include "proxy_wasm_intrinsics.h"
#include "google/protobuf/text_format.h"
#include "samples/set_reset_cookie/cookie_config.pb.h"
#include <algorithm>
#include <string>
#include <utility>
#include <vector>

using serviceextensions::cookie_manager::CookieConfig;
using serviceextensions::cookie_manager::CookieManagerConfig;
using serviceextensions::cookie_manager::CookieOperation;

class CookieManagerRootContext : public RootContext {
 public:
  explicit CookieManagerRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t config_size) override {
    // Handle empty configuration
    if (config_size == 0) {
      LOG_WARN("Empty configuration provided, no cookies will be managed");
      return true;  // Empty config is valid, just does nothing
    }
    
    auto configuration_data = getBufferBytes(WasmBufferType::PluginConfiguration,
                                            0, config_size);
    if (!configuration_data) {
      LOG_ERROR("Failed to retrieve configuration data buffer");
      return false;
    }
    
    CookieManagerConfig config;
    
    // Attempt to parse the protobuf configuration
    if (!google::protobuf::TextFormat::ParseFromString(configuration_data->toString(), &config)) {
      LOG_ERROR("Failed to parse cookie manager configuration as text protobuf. "
                "Please ensure configuration follows the text protobuf format. "
                "Example: cookies { name: \"session\" value: \"abc\" }");
      return false;
    }
    
    // Validate parsed configuration
    if (config.cookies_size() == 0) {
      LOG_WARN("Configuration parsed successfully but contains no cookie definitions");
      return true;
    }
    
    int valid_cookies = 0;
    
    for (const auto& cookie_config : config.cookies()) {
      // Validate required fields based on operation type
      if (cookie_config.name().empty()) {
        LOG_ERROR("Cookie configuration missing required 'name' field, skipping");
        continue;
      }
      
      if (cookie_config.operation() == CookieOperation::SET || 
          cookie_config.operation() == CookieOperation::OVERWRITE) {
        if (cookie_config.value().empty()) {
          LOG_WARN(absl::StrCat("Cookie '", cookie_config.name(),
                              "' has SET/OVERWRITE operation but empty value"));
        }
      }
      
      cookie_configs_.push_back(cookie_config);
      valid_cookies++;
      
     // Log configuration for debugging
      LOG_DEBUG(absl::StrCat(
        "Configure cookie name=", cookie_config.name(),
        ", operation=", static_cast<int>(cookie_config.operation())
      ));
    }
    
    if (valid_cookies == 0) {
      LOG_ERROR("No valid cookie configurations found after validation");
      return false;
    }
    
    LOG_INFO(absl::StrCat(
      "Successfully loaded ", valid_cookies, " cookie configuration(s)"
    ));         
    return true;
  }

  const std::vector<CookieConfig>& getCookieConfigs() const {
    return cookie_configs_;
  }

 private:
  std::vector<CookieConfig> cookie_configs_;
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
  // A vector (not a map) so duplicate cookie names and original order are
  // preserved.
  std::vector<std::pair<std::string, std::string>> request_cookies_;

  // Parse cookies from the Cookie header. Splits on ';' and trims whitespace so
  // variance in spacing around the separator is tolerated.
  void parseRequestCookies() {
    auto cookie_header = getRequestHeader("Cookie");
    if (!cookie_header) {
      return;
    }

    const std::string cookies = cookie_header->toString();
    for (absl::string_view cookie_pair : absl::StrSplit(cookies, ';')) {
      cookie_pair = absl::StripAsciiWhitespace(cookie_pair);
      if (cookie_pair.empty()) {
        continue;
      }
      std::vector<absl::string_view> parts =
          absl::StrSplit(cookie_pair, absl::MaxSplits('=', 1));
      if (parts.size() == 2) {
        request_cookies_.emplace_back(
            std::string(absl::StripAsciiWhitespace(parts[0])),
            std::string(absl::StripAsciiWhitespace(parts[1])));
      }
    }
  }

  // Process cookie deletions before CDN cache
  void processCookieDeletions() {
    const auto& configs = root_->getCookieConfigs();
    bool modified = false;

    for (const auto& config : configs) {
      if (config.operation() != CookieOperation::DELETE) {
        continue;
      }
      // A request may carry several cookies with the same name (e.g. set for
      // different paths), so remove every occurrence.
      const auto removed = std::erase_if(
          request_cookies_,
          [&](const auto& cookie) { return cookie.first == config.name(); });
      if (removed > 0) {
        modified = true;
        LOG_INFO(absl::StrCat("Marking cookie for deletion before CDN cache: ",
                              config.name()));
      }
    }

    if (modified) {
      rebuildCookieHeader();
    }
  }

  // Rebuild Cookie header from the remaining cookies
  void rebuildCookieHeader() {
    if (request_cookies_.empty()) {
      removeRequestHeader("Cookie");
      return;
    }

    std::vector<std::string> remaining_cookies;
    remaining_cookies.reserve(request_cookies_.size());
    for (const auto& cookie : request_cookies_) {
      remaining_cookies.push_back(absl::StrCat(cookie.first, "=", cookie.second));
    }
    replaceRequestHeader("Cookie", absl::StrJoin(remaining_cookies, "; "));
  }

  // Process SET and OVERWRITE operations
  void processCookieOperations() {
    const auto& configs = root_->getCookieConfigs();
    
    for (const auto& config : configs) {
      if (config.operation() == CookieOperation::SET) {
        setCookie(config);
      } else if (config.operation() == CookieOperation::OVERWRITE) {
        overwriteCookie(config);
      }
    }
  }

  // Set or reset a cookie
  void setCookie(const CookieConfig& config) {
    std::string cookie_value = absl::StrCat(config.name(), "=", config.value());
    
    // Add Path attribute
    absl::StrAppend(&cookie_value, "; Path=", config.path());
    
    // Add Domain attribute if specified
    if (!config.domain().empty()) {
      absl::StrAppend(&cookie_value, "; Domain=", config.domain());
    }
    
    // Add Max-Age for persistent cookies (session if -1)
    if (config.max_age() > 0) {
      absl::StrAppend(&cookie_value, "; Max-Age=", config.max_age());
    }
    
    // Add security attributes
    if (config.http_only()) {
      absl::StrAppend(&cookie_value, "; HttpOnly");
    }
    
    if (config.secure()) {
      absl::StrAppend(&cookie_value, "; Secure");
    }
    
    if (config.same_site_strict()) {
      absl::StrAppend(&cookie_value, "; SameSite=Strict");
    }
    
    addResponseHeader("Set-Cookie", cookie_value);
    
    // Matches the Max-Age logic above: only a positive max_age is persistent.
    const char* log_type = (config.max_age() > 0) ? "persistent" : "session";
    // Cookie value intentionally not logged (may be sensitive).
    LOG_INFO(absl::StrCat("Setting ", log_type, " cookie: ", config.name()));
  }

  // Remove existing Set-Cookie headers for this cookie only (other cookies are
  // left intact), then set the new value or expire the cookie.
  void removeExistingSetCookie(const std::string& name) {
    const std::string prefix = absl::StrCat(name, "=");
    std::vector<std::string> kept;
    bool removed = false;

    for (const auto& header : getResponseHeaderPairs()->pairs()) {
      if (!absl::EqualsIgnoreCase(header.first, "Set-Cookie")) {
        continue;
      }
      if (absl::StartsWith(absl::StripLeadingAsciiWhitespace(header.second),
                           prefix)) {
        removed = true;
      } else {
        kept.emplace_back(header.second);
      }
    }

    if (!removed) {
      return;
    }
    // The API can only clear a header by name, so re-add the ones to keep.
    removeResponseHeader("Set-Cookie");
    for (const auto& value : kept) {
      addResponseHeader("Set-Cookie", value);
    }
  }

  // Overwrite or remove existing Set-Cookie headers
  void overwriteCookie(const CookieConfig& config) {
    removeExistingSetCookie(config.name());

    // If value is not empty, set the new cookie
    if (!config.value().empty()) {
      setCookie(config);
      LOG_INFO(absl::StrCat("Overwriting existing cookie: ", config.name()));
    } else {
      // Complete removal - set expired cookie
      std::string expire_cookie = absl::StrCat(
          config.name(), "=; Path=", config.path(), "; Max-Age=0");

      if (!config.domain().empty()) {
        absl::StrAppend(&expire_cookie, "; Domain=", config.domain());
      }

      addResponseHeader("Set-Cookie", expire_cookie);
      LOG_INFO(absl::StrCat("Removing Set-Cookie directive for: ", config.name()));
    }
  }
};

static RegisterContextFactory register_CookieManagerContext(
    CONTEXT_FACTORY(CookieManagerHttpContext),
    ROOT_FACTORY(CookieManagerRootContext));
// [END serviceextensions_plugin_set_reset_cookie]
