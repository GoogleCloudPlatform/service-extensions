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
#include <boost/url/parse.hpp>
#include <boost/url/url.hpp>

#include "absl/strings/match.h"
#include "absl/strings/str_cat.h"
#include "proxy_wasm_intrinsics.h"

constexpr std::string_view a_path = "/v1/";
constexpr std::string_view b_path = "/v2/";
constexpr int percentile = 50;

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto path = getRequestHeader(":path")->view();

    // Checks if the current request is eligible to be served by v2 file.
    //
    // The decision is made by hashing the userID into an integer
    // value between 0 and 99, then comparing the hash to a predefined
    // percentile. If the hash value is less than or equal to the percentile,
    // the request is served by the v2 file. Otherwise, it is served by the
    // original file.
    const auto user = extractUserFromPath(path);
    if (absl::StartsWithIgnoreCase(path, a_path) && user != "" &&
        (std::hash<std::string_view>{}(user) % 100 <= percentile)) {
      std::string new_path = absl::StrCat(b_path, path.substr(a_path.length()));
      replaceRequestHeader(":path", new_path);
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  static std::string_view extractUserFromPath(std::string_view path) {
    const boost::system::result<boost::urls::url_view> url =
        boost::urls::parse_relative_ref(path);
    auto it = url->params().find("user");
    if (it != url->params().end()) {
      return (*it).value;
    }
    return "";
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_ab_testing]
