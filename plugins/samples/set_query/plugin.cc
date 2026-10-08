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

// [START serviceextensions_plugin_set_query]
#include <boost/url/encode.hpp>
#include <boost/url/parse.hpp>
#include <boost/url/rfc/pchars.hpp>
#include <boost/url/url.hpp>

#include "proxy_wasm_intrinsics.h"

constexpr size_t kMaxPathLength = 4096;

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    WasmDataPtr path = getRequestHeader(":path");
    if (!path) {
      LOG_DEBUG("No :path header found");
      return FilterHeadersStatus::Continue;
    }

    std::string_view path_view = path->view();
    if (path_view.length() > kMaxPathLength) {
      LOG_WARN("Path too long (" + std::to_string(path_view.length()) +
               " bytes), skipping processing");
      return FilterHeadersStatus::Continue;
    }

    boost::system::result<boost::urls::url> url =
        boost::urls::parse_uri_reference(path_view);
    if (!url) {
      LOG_WARN("Failed to parse URL: " + std::string(path_view));
      return FilterHeadersStatus::Continue;
    }

    boost::urls::encoding_opts opt;
    opt.space_as_plus = true;

    std::string val = boost::urls::encode("new val", boost::urls::pchars, opt);

    // Optional: erase the key to put the new pair at the end.
    url->params(opt).erase("key");
    url->params(opt).set("key", val);

    auto result = replaceRequestHeader(":path", url->encoded_resource());
    if (result != WasmResult::Ok) {
      LOG_ERROR("Failed to replace :path header, error: " +
                std::to_string(static_cast<int>(result)));
    } else {
      LOG_DEBUG("Successfully updated :path to: " +
                std::string(url->encoded_resource()));
    }

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_set_query]
