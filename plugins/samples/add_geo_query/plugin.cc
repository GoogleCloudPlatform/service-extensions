// Copyright 2026 Google LLC
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

// [START serviceextensions_plugin_country_query]
#include <string>
#include <string_view>
#include "absl/strings/str_cat.h"
#include "boost/url/parse.hpp"
#include "boost/url/url.hpp"
#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Default country value if geo data is not available
    std::string_view country_value = "unknown";

    auto client_region = getProperty({"request", "client_region"});
    if (client_region) {
      auto client_region_view = client_region.value()->view();
      if (!client_region_view.empty()) {
        country_value = client_region_view;
      }
    }

    LOG_INFO(absl::StrCat("country: ", country_value));

    WasmDataPtr path = getRequestHeader(":path");
    if (path) {
      boost::system::result<boost::urls::url> url =
          boost::urls::parse_uri_reference(path->view());
      if (url) {
        url->params().set("country", country_value);
        replaceRequestHeader(":path", url->buffer());
      }
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_country_query]
