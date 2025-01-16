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

// [START serviceextensions_plugin_set_query]
#include <boost/url/encode.hpp>
#include <boost/url/parse.hpp>
#include <boost/url/rfc/pchars.hpp>
#include <boost/url/url.hpp>

#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    WasmDataPtr path = getRequestHeader(":path");
    if (path) {
      boost::system::result<boost::urls::url> url =
          boost::urls::parse_uri_reference(path->view());
      if (url) {
        // Optional: encode query param spaces as "+" instead of "%20"
        boost::urls::encoding_opts opt;
        opt.space_as_plus = true;
        std::string val =
            boost::urls::encode("new val", boost::urls::pchars, opt);
        // Optional: erase the key to put the new pair at the end.
        url->params(opt).erase("key");
        url->params(opt).set("key", val);
        replaceRequestHeader(":path", url->encoded_resource());
      }
    }
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_set_query]
