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

// [START serviceextensions_plugin_geo_routing]
#include <string_view>
#include <vector>

#include "proxy_wasm_intrinsics.h"

constexpr std::string_view kGeoHeaderKey = "x-country-code";

// HTTP context class that handles incoming HTTP requests and sets geographic
// routing headers based on client location.
//
// This plugin reads the client's geographic region from request properties
// provided by the load balancer and sets a custom header that can be used
// by URL Map routing rules to direct traffic to geographically appropriate
// backend services.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Retrieve the client's geographic region from load balancer properties.
    auto country_property = getProperty({"request", "client_region"});

    if (country_property) {
      const auto country_view = country_property.value()->view();

      if (!country_view.empty()) {
        // Set the x-country-code header with the client's country code.
        replaceRequestHeader(kGeoHeaderKey, country_view);
        return FilterHeadersStatus::Continue;
      }
    }

    removeRequestHeader(kGeoHeaderKey);
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_geo_routing]
