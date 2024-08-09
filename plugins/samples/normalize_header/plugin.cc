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

// [START serviceextensions_plugin_normalize_header]
#include "proxy_wasm_intrinsics.h"
#include "absl/strings/ascii.h"

// Determines client device type based on request headers.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Check "Sec-CH-UA-Mobile" header first (highest priority)
    const auto mobile_header = getRequestHeader("Sec-CH-UA-Mobile");
    if (mobile_header && mobile_header->toString() == "?1") {
      addRequestHeader("client-device-type", "mobile");
      return FilterHeadersStatus::Continue;
    }

    // Check "User-Agent" header for mobile substring (case insensitive)
    const auto user_agent = getRequestHeader("User-Agent");
    if (user_agent) {
      const auto user_agent_str = user_agent->toString();
      if (std::string::npos != absl::AsciiStrToLower(user_agent_str).find("mobile")) {
        addRequestHeader("client-device-type", "mobile");
        return FilterHeadersStatus::Continue;
      }
    }

    // No specific device type identified, set to "unknown"
    addRequestHeader("client-device-type", "unknown");
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_normalize_header]
