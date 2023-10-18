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

// [START serviceextensions_query_log]
#include <boost/url/parse.hpp>
#include <boost/url/url.hpp>

#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    WasmDataPtr path = getRequestHeader(":path");
    if (path) {
      std::string token = "<missing>";
      boost::system::result<boost::urls::url_view> url =
          boost::urls::parse_uri_reference(path->view());
      if (url) {
        auto it = url->params().find("token");
        if (it != url->params().end()) {
          token = (*it).value;
        }
      }
      LOG_INFO("token: " + token);
    }
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_query_log]
