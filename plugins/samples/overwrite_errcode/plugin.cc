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

// [START serviceextensions_plugin_overwrite_errcode]
#include "absl/strings/numbers.h"
#include "absl/strings/str_cat.h"
#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    const auto response_status = getResponseHeader(":status");
    int response_code;
    if (response_status &&
        absl::SimpleAtoi(response_status->view(), &response_code) &&
        (response_code / 100 == 5)) {
      replaceResponseHeader(":status",
                            absl::StrCat(mapResponseCode(response_code)));
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  int mapResponseCode(int response_code) {
    // Example: remap all 5xx responses to 404.
    return (response_code / 100 == 5) ? 404 : response_code;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_overwrite_errcode]