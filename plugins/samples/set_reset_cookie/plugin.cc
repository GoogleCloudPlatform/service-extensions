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
#include <string>
#include <utility>
#include <vector>

#include "absl/strings/numbers.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_join.h"
#include "absl/strings/str_split.h"
#include "proxy_wasm_intrinsics.h"

// Cookie operation types.
enum class CookieOp { SET, DELETE, OVERWRITE };

// Parsed cookie configuration.
struct CookieConfig {
  CookieOp operation = CookieOp::SET;
  std::string name;
  std::string value;
  std::string path = "/";
  std::string domain;
  int max_age = -1;  // -1 for session cookie, >0 for persistent
  bool http_only = false;
  bool secure = false;
  bool same_site_strict = false;
};

class CookieManagerRootContext : public RootContext {
 public:
  explicit CookieManagerRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t config_size) override {
    if (config_size == 0) {
      LOG_WARN("Empty configuration provided, no cookies will be managed");
      return true;
    }

    auto config_data = getBufferBytes(WasmBufferType::PluginConfiguration, 0,
                                      config_size);
    if (!config_data) {
      LOG_ERROR("Failed to retrieve configuration data buffer");
      return false;
    }

    // Parse pipe-delimited config lines:
    // OPERATION|name|value|path|domain|max_age|http_only|secure|same_site_strict
    std::string config_str = config_data->toString();
    for (absl::string_view line : absl::StrSplit(config_str, '\n')) {
      // Skip empty lines and comments.
      if (line.empty() || line[0] == '#') continue;

      std::vector<std::string> fields = absl::StrSplit(line, '|');
      if (fields.size() < 2) {
        LOG_ERROR(absl::StrCat("Invalid config line: ", line));
        continue;
      }

      CookieConfig cookie;

      // Parse operation.
      if (fields[0] == "SET") {
        cookie.operation = CookieOp::SET;
      } else if (fields[0] == "DELETE") {
        cookie.operation = CookieOp::DELETE;
      } else if (fields[0] == "OVERWRITE") {
        cookie.operation = CookieOp::OVERWRITE;
      } else {
        LOG_ERROR("Unknown operation: " + fields[0]);
        continue;
      }

      cookie.name = fields[1];
      if (cookie.name.empty()) {
        LOG_ERROR("Cookie name cannot be empty");
        continue;
      }

      // Parse optional fields.
      if (fields.size() > 2) cookie.value = fields[2];
      if (fields.size() > 3 && !fields[3].empty()) cookie.path = fields[3];
      if (fields.size() > 4) cookie.domain = fields[4];
      if (fields.size() > 5 && !fields[5].empty()) {
        if (!absl::SimpleAtoi(fields[5], &cookie.max_age)) {
          LOG_ERROR(absl::StrCat("Invalid max_age value: ", fields[5]));
          continue;
        }
      }
      if (fields.size() > 6) cookie.http_only = (fields[6] == "true");
      if (fields.size() > 7) cookie.secure = (fields[7] == "true");
      if (fields.size() > 8) cookie.same_site_strict = (fields[8] == "true");

      cookie_configs_.push_back(cookie);
    }

    if (cookie_configs_.empty()) {
      LOG_WARN("No valid cookie configurations found, no cookies will be managed");
      return true;
    }

    LOG_INFO(absl::StrCat("Successfully loaded ", cookie_configs_.size(),
                           " cookie configuration(s)"));
    return true;
  }

  const std::vector<CookieConfig>& getCookieConfigs() const {
    return cookie_configs_;
  }

 private:
  std::vector<CookieConfig> cookie_configs_;
};

// HTTP context for cookie management operations.
class CookieManagerHttpContext : public Context {
 public:
  explicit CookieManagerHttpContext(uint32_t id, RootContext* root)
      : Context(id, root),
        root_(static_cast<CookieManagerRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    parseRequestCookies();
    processCookieDeletions();
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    processCookieOperations();
    return FilterHeadersStatus::Continue;
  }

 private:
  CookieManagerRootContext* root_;
  // Preserve original cookie order using a vector of pairs.
  std::vector<std::pair<std::string, std::string>> request_cookies_;

  // Parse cookies from the Cookie request header.
  void parseRequestCookies() {
    auto cookie_header = getRequestHeader("Cookie");
    if (!cookie_header || cookie_header->size() == 0) return;

    for (absl::string_view pair : absl::StrSplit(cookie_header->view(), "; ")) {
      std::vector<std::string> parts =
          absl::StrSplit(pair, absl::MaxSplits('=', 1));
      if (parts.size() == 2) {
        request_cookies_.emplace_back(parts[0], parts[1]);
      }
    }
  }

  // Remove cookies marked for DELETE from the request Cookie header.
  void processCookieDeletions() {
    bool modified = false;
    for (const auto& config : root_->getCookieConfigs()) {
      if (config.operation != CookieOp::DELETE) continue;
      for (auto it = request_cookies_.begin(); it != request_cookies_.end();
           ++it) {
        if (it->first == config.name) {
          request_cookies_.erase(it);
          modified = true;
          LOG_INFO("Marking cookie for deletion before CDN cache: " +
                   config.name);
          break;
        }
      }
    }

    if (modified) {
      if (request_cookies_.empty()) {
        removeRequestHeader("Cookie");
      } else {
        std::vector<std::string> parts;
        for (const auto& [name, value] : request_cookies_) {
          parts.push_back(absl::StrCat(name, "=", value));
        }
        replaceRequestHeader("Cookie", absl::StrJoin(parts, "; "));
      }
    }
  }

  // Process SET and OVERWRITE operations on response headers.
  void processCookieOperations() {
    for (const auto& config : root_->getCookieConfigs()) {
      if (config.operation == CookieOp::SET) {
        addSetCookieHeader(config);
      } else if (config.operation == CookieOp::OVERWRITE) {
        overwriteCookie(config);
      }
    }
  }

  // Build a Set-Cookie header value string from config attributes.
  std::string buildSetCookieValue(const CookieConfig& config) {
    std::string val = absl::StrCat(config.name, "=", config.value);
    absl::StrAppend(&val, "; Path=", config.path);
    if (!config.domain.empty()) {
      absl::StrAppend(&val, "; Domain=", config.domain);
    }
    if (config.max_age > 0) {
      absl::StrAppend(&val, "; Max-Age=", config.max_age);
    }
    if (config.http_only) {
      absl::StrAppend(&val, "; HttpOnly");
    }
    if (config.secure) {
      absl::StrAppend(&val, "; Secure");
    }
    if (config.same_site_strict) {
      absl::StrAppend(&val, "; SameSite=Strict");
    }
    return val;
  }

  // Add a new Set-Cookie response header.
  void addSetCookieHeader(const CookieConfig& config) {
    addResponseHeader("Set-Cookie", buildSetCookieValue(config));
    std::string log_type = (config.max_age == -1) ? "session" : "persistent";
    LOG_INFO("Setting " + log_type + " cookie: " + config.name);
  }

  // Overwrite an existing Set-Cookie header for the target cookie name,
  // preserving other Set-Cookie headers.
  // Note: The proxy-wasm host combines multiple Set-Cookie headers into a
  // single comma-separated value, so we split and reconstruct. This means
  // origin cookies using the Expires attribute (which contains a comma in its
  // date format) will be corrupted. Use Max-Age instead of Expires.
  void overwriteCookie(const CookieConfig& config) {
    auto existing = getResponseHeader("Set-Cookie");
    removeResponseHeader("Set-Cookie");

    // Preserve non-matching Set-Cookie values from the combined header.
    if (existing && existing->size() > 0) {
      std::string prefix = absl::StrCat(config.name, "=");
      for (absl::string_view cookie :
           absl::StrSplit(existing->view(), ", ")) {
        if (cookie.substr(0, prefix.size()) != prefix) {
          addResponseHeader("Set-Cookie", std::string(cookie));
        }
      }
    }

    // Set the new value or expire the cookie.
    if (!config.value.empty()) {
      addSetCookieHeader(config);
    } else {
      std::string expire = absl::StrCat(config.name, "=; Path=", config.path,
                                         "; Max-Age=0");
      if (!config.domain.empty()) {
        absl::StrAppend(&expire, "; Domain=", config.domain);
      }
      addResponseHeader("Set-Cookie", expire);
      LOG_INFO("Removing Set-Cookie directive for: " + config.name);
    }
  }
};

static RegisterContextFactory register_CookieManagerContext(
    CONTEXT_FACTORY(CookieManagerHttpContext),
    ROOT_FACTORY(CookieManagerRootContext));
// [END serviceextensions_plugin_set_reset_cookie]
