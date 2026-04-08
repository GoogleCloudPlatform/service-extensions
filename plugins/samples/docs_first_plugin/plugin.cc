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

// [START serviceextensions_plugin_docs_first_plugin]
#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    LOG_INFO("onRequestHeaders: hello from wasm");

    // Route Extension example: host rewrite
    if (replaceRequestHeader(":authority", "service-extensions.com") != WasmResult::Ok) {
      LOG_ERROR("Failed to replace :authority header");
    }
    if (replaceRequestHeader(":path", "/") != WasmResult::Ok) {
      LOG_ERROR("Failed to replace :path header");
    }
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    LOG_INFO("onResponseHeaders: hello from wasm");
    
    // Traffic Extension example: add response header
    if (addResponseHeader("hello", "service-extensions") != WasmResult::Ok) {
      LOG_ERROR("Failed to add response header");
    }
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_docs_first_plugin]
