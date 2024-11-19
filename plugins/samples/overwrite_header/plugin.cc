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

// [START serviceextensions_plugin_overwrite_header]
#include "proxy_wasm_intrinsics.h"

// This sample replaces an HTTP header with the given key and value.
// Unlike `addRequestHeader` which appends values to existing headers,
// this plugin overwrites the entire value for the specified key if the
// header already exists or create it with the new value.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Change the key and value according to your needs.
    const auto header_key = "RequestHeader";
    const auto header = getRequestHeader(header_key);
    // It will only replace the header if it already exists.
    if (header->size() > 0) {
      replaceRequestHeader(header_key, "changed");
    }

    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    // Unlike the previous example, the header will be added if it doesn't exist
    // or updated if it already does.
    // Change the key and value according to your needs.
    replaceResponseHeader("ResponseHeader", "changed");

    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_overwrite_header]
