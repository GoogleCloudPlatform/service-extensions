// Copyright 2023 Google LLC
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

#include <ctime>
#include <string>

#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    std::string path = getRequestHeader(":path")->toString();

    const std::string default_file = "/file1.blah";
    const std::string experiment_file = "/file2.blah";
    if (path.length() >= default_file.length() && std::equal(default_file.rbegin(), default_file.rend(), path.rbegin())) {
      bool serve_alternative_file = (rand() % 2 == 1);
      if (serve_alternative_file) {
        const std::string truncated_path = path.substr(0, path.length() - default_file.length());
        replaceRequestHeader(":path", truncated_path + experiment_file);
      }
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
