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

// [START serviceextensions_plugin_block_request]
#include "absl/strings/match.h"
#include "proxy_wasm_intrinsics.h"

// Checks the client referrer header for a bad value,
// serve a synthetic 404 block with a basic html response.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto referer = getRequestHeader("Referer");
    // Change the value to whatever is considered a bad URL for your needs.
    if (referer &&
        absl::StrContainsIgnoreCase(referer->view(), "forbidden-site")) {
        sendLocalResponse(404, "", "Not found.\n", {});
        return FilterHeadersStatus::StopAllIterationAndWatermark;
      }

    addRequestHeader("Allowed", "true");
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_block_request]
