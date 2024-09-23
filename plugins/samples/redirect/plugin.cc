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
#include "absl/strings/str_cat.h"
#include "proxy_wasm_intrinsics.h"

constexpr std::string_view old_path_prefix = "/foo/";
constexpr std::string_view new_path_prefix = "/bar/";

// This sample redirects any requests to paths starting with /foo/ to instead
// use path /bar/.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    auto path = getRequestHeader(":path")->toString();
    if (absl::StartsWith(path, old_path_prefix)) {
      std::string new_path =
          absl::StrCat(new_path_prefix, path.substr(old_path_prefix.length()));
      sendLocalResponse(301, "", absl::StrCat("Content moved to ", new_path),
                        {{"Location", new_path}});
      return FilterHeadersStatus::ContinueAndEndStream;
    }
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_redirect]
