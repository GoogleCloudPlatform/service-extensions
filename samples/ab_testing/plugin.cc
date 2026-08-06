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

// [START serviceextensions_ab_testing]
#include <ctime>
#include <string>
#include <string_view>

#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 private:
  static constexpr std::string_view DEFAULT_FILE_NAME = "/file1.blah";
  static constexpr std::string_view EXPERIMENT_FILE_NAME = "/file2.blah";
  static constexpr int CHANGE_FILE_PERCENT_PROBABILITY = 20;

  static bool endsWith(std::string_view str, std::string_view suffix) {
    if (str.length() < suffix.length()) {
        return false;
    }
    return str.substr(str.length() - suffix.length()) == suffix;
  }
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    WasmDataPtr path_header = getRequestHeader(":path");
    if (!path_header) {
      return FilterHeadersStatus::Continue;
    }
    std::string_view path_view = path_header->view();

    if (endsWith(path_view, DEFAULT_FILE_NAME)) {
      // Path ends with DEFAULT_FILE_NAME. Roll the dice and see if it should
      // be replaced with the EXPERIMENT_FILE_NAME.
      bool change_file = (rand() % 100 < CHANGE_FILE_PERCENT_PROBABILITY);
      if (change_file) {
        // Truncate DEFAULT_FILE_NAME from the existing path.
        const std::string_view truncated_path = (
          path_view.substr(0, path_view.length() - DEFAULT_FILE_NAME.length()));

        replaceRequestHeader(
          ":path",
          std::string(truncated_path) + std::string(EXPERIMENT_FILE_NAME)
        );
      }
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_ab_testing]
