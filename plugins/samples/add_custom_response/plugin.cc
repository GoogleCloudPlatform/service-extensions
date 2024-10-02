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

// [START serviceextensions_plugin_add_custom_response]
#include "absl/strings/numbers.h"
#include "proxy_wasm_intrinsics.h"

constexpr std::string_view redirect_page =
    "http://storage.googleapis.com/www.example.com/server-error.html";

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    const WasmDataPtr response_status = getResponseHeader(":status");
    int response_code;
    if (response_status &&
        absl::SimpleAtoi(response_status->view(), &response_code) &&
        (response_code / 100 == 5)) {
      sendLocalResponse(301, "", "",
                        {{"Orign-Status", response_status->toString()},
                         {"Location", std::string{redirect_page}}});
      return FilterHeadersStatus::ContinueAndEndStream;
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_add_custom_response]
