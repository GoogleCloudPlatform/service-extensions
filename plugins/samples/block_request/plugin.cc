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
#include <string>

#include "absl/strings/match.h"
#include "proxy_wasm_intrinsics.h"

constexpr absl::string_view kAllowedReferer = "safe-site.com";

// Checks whether the client's Referer header matches an expected domain. If
// not, generate a 403 Forbidden response.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto referer = getRequestHeader("Referer");
    // Check if referer match with the expected domain.
    if (!referer || !absl::StrContains(referer->view(), kAllowedReferer)) {
      const auto requestId = generateRandomRequestId();
      sendLocalResponse(403, "", "Forbidden - Request ID: " + requestId, {});
      LOG_INFO("Forbidden - Request ID: " + requestId);
      return FilterHeadersStatus::StopAllIterationAndWatermark;
    }

    // Change it to a meaningful name according to your needs.
    addRequestHeader("my-plugin-allowed", "true");
    return FilterHeadersStatus::Continue;
  }

 private:
  // Generate a unique random request ID.
  std::string generateRandomRequestId() {
    // Wasm VM does not support the random generation
    // that involves a file system operation.
    using namespace std::chrono_literals;
    const auto ts = std::chrono::high_resolution_clock::now();
    const auto ns = ts.time_since_epoch() / 1ns;
    return std::to_string(ns);
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_block_request]
