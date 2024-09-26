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

// [START serviceextensions_plugin_ab_testing]
#include "absl/strings/match.h"
#include "absl/strings/str_cat.h"
#include "proxy_wasm_intrinsics.h"

constexpr std::string_view a_path = "/file1.png";
constexpr std::string_view b_path = "/file2.png";
constexpr int percentile = 50;

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto path = getRequestHeader(":path")->view();

    // Checks if the current request is eligible to be served by file B.
    //
    // The decision is made by hashing the request path into an integer
    // value between 0 and 99, then comparing the hash to a predefined
    // percentile. If the hash value is less than or equal to the percentile,
    // the request is served by file B. Otherwise, it is served by the original
    // file.
    if (absl::StartsWithIgnoreCase(path, a_path) &&
        (std::hash<std::string_view>{}(path) % 100 <= percentile)) {
      std::string new_path = absl::StrCat(b_path, path.substr(a_path.length()));
      replaceRequestHeader(":path", new_path);
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_ab_testing]
