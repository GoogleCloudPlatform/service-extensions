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
#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Default country value if geo data is not available
    std::string country_value = "unknown";

    // Try to read the client_region attribute from request properties.
    auto client_region = getProperty({"request", "client_region"});
    if (client_region) {
      auto client_region_view = client_region.value()->view();
      if (!client_region_view.empty()) {
        country_value = std::string(client_region_view);
      }
    }

    // Log the country value for GCP logs
    LOG_INFO("country: " + country_value);

    // Get current path and add country query parameter
    auto path_header = getRequestHeader(":path");
    if (path_header) {
      std::string new_path;
      auto path_view = path_header->view();

      // Check if query string already exists
      if (path_view.find('?') == std::string_view::npos) {
        new_path = std::string(path_view) + "?country=" + country_value;
      } else {
        new_path = std::string(path_view) + "&country=" + country_value;
      }

      replaceRequestHeader(":path", new_path);
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_country_query]
