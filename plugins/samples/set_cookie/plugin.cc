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

// [START serviceextensions_plugin_set_cookie]
#include "absl/strings/match.h"
#include "proxy_wasm_intrinsics.h"

constexpr absl::string_view kRangeStatusSuccess = "2";  // 2XX

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    const auto status = getResponseHeader(":status");
    // Check if response status is part of the success range (2XX).
    if (status &&
        absl::StartsWithIgnoreCase(status->view(), kRangeStatusSuccess)) {
      // Change the new cookie according to your needs.
      addResponseHeader("Set-Cookie",
                        "your_cookie_name=cookie_value; Path=/; HttpOnly");
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_set_cookie]
