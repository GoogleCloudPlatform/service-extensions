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

// [START serviceextensions_plugin_country_query]
#include <string>
#include <string_view>

#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Default country value if geo data is not available
    std::string_view country_value = "unknown";

    auto client_region = getProperty({"request", "client_region"});
    if (client_region) {
      auto client_region_view = client_region.value()->view();
      if (!client_region_view.empty()) {
        country_value = client_region_view;
      }
    }

    std::string log_msg = "country: ";
    log_msg.append(country_value);
    LOG_INFO(log_msg);

    auto path_header = getRequestHeader(":path");
    std::string_view path_view = path_header ? path_header->view() : "";

    std::string new_path;
    new_path.reserve(path_view.size() + 10 + country_value.size());
    new_path.append(path_view);

    // Check if query string already exists
    if (path_view.find('?') == std::string_view::npos) {
      new_path.append("?country=");
    } else {
      new_path.append("&country=");
    }
    new_path.append(country_value);

    replaceRequestHeader(":path", new_path);

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_country_query]
