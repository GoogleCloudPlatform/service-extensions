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

// [START serviceextensions_plugin_redirect]
#include "absl/strings/match.h"
#include "proxy_wasm_intrinsics.h"

// This sample may redirects the request for other URL according to the URL
// requested.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto location = getRequestHeader("Location");
    // Change the values according to your needs.
    if (location && absl::StrContainsIgnoreCase(
                        location->view(), "service-extensions.com/main")) {
      sendLocalResponse(
          301, "", "",
          {{"Location", "https://service-extensions.com/redirect"}});

      return FilterHeadersStatus::StopAllIterationAndWatermark;
    }
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_redirect]
