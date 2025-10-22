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

// [START serviceextensions_plugin_device_type]
#include "absl/strings/ascii.h"
#include "absl/strings/match.h"
#include "proxy_wasm_intrinsics.h"

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  // Define all keyword lists as static variables
  static const std::vector<std::string>& BotKeywords() {
    static const auto* bots = new std::vector<std::string>{
        "bot", "crawler", "spider", "googlebot", "bingbot", "slurp",
        "duckduckbot", "yandexbot", "baiduspider"};
    return *bots;
  }

  static const std::vector<std::string>& TabletKeywords() {
    static const auto* tablets = new std::vector<std::string>{
        "ipad", "tablet", "kindle", "tab", "playbook", "nexus 7",
        "sm-t", "pad", "gt-p"};
    return *tablets;
  }

  static const std::vector<std::string>& AndroidIndicators() {
    static const auto* indicators = new std::vector<std::string>{
        "tablet", "tab", "pad"};
    return *indicators;
  }

  static const std::vector<std::string>& MobileKeywords() {
    static const auto* mobiles = new std::vector<std::string>{
        "mobile", "android", "iphone", "ipod", "blackberry",
        "windows phone", "webos", "iemobile", "opera mini"};
    return *mobiles;
  }

  static const std::vector<std::string>& DesktopKeywords() {
    static const auto* desktops = new std::vector<std::string>{
        "mozilla", "chrome", "safari", "firefox",
        "msie", "opera", "edge", "chromium", "vivaldi"};
    return *desktops;
  }
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    std::string user_agent;
    const auto user_agent_ptr = getRequestHeader("user-agent");
    
    if (user_agent_ptr) {
      user_agent = absl::AsciiStrToLower(user_agent_ptr->toString());
    }

    const std::string device_type = DetectDeviceType(user_agent);
    replaceRequestHeader("x-device-type", device_type);

    return FilterHeadersStatus::Continue;
  }

 private:
  std::string DetectDeviceType(const std::string& ua) const {
    if (IsBot(ua)) return "bot";
    if (IsTablet(ua)) return "tablet";
    if (IsMobile(ua)) return "phone";
    if (IsDesktop(ua)) return "desktop";
    return "other";
  }

  bool IsBot(const std::string& ua) const {
    return ContainsAny(ua, MyRootContext::BotKeywords());
  }

  bool IsTablet(const std::string& ua) const {
    if (ContainsAny(ua, MyRootContext::TabletKeywords())) return true;
    
    if (absl::StrContains(ua, "android")) {
      return ContainsAny(ua, MyRootContext::AndroidIndicators());
    }
    return false;
  }

  bool IsMobile(const std::string& ua) const {
    return ContainsAny(ua, MyRootContext::MobileKeywords());
  }

  bool IsDesktop(const std::string& ua) const {
    return ContainsAny(ua, MyRootContext::DesktopKeywords());
  }

  bool ContainsAny(const std::string& ua,
                   const std::vector<std::string>& subs) const {
    for (const auto& sub : subs) {
      if (absl::StrContains(ua, sub)) return true;
    }
    return false;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_device_type]
