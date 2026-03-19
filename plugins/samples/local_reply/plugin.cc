// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// [START serviceextensions_plugin_hello_world]

#include "proxy_wasm_intrinsics.h"

class HelloWorldRootContext : public RootContext {

public:
  explicit HelloWorldRootContext(uint32_t id, std::string_view root_id) : RootContext(id, root_id) {}
};

class HelloWorldHttpContext : public Context {
public:
  explicit HelloWorldHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}
  FilterHeadersStatus onRequestHeaders(uint32_t, bool) override {
    // Send a local response with status 200 and "Hello World" as body
    sendLocalResponse(200, "", "Hello World",
                      {{"Content-Type", "text/plain"}, {":status", "200"}});
    return FilterHeadersStatus::StopIteration;
  }

  FilterDataStatus onRequestBody(size_t body_size, bool end_stream) override {
    return FilterDataStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    return FilterHeadersStatus::Continue;
  }

};

static RegisterContextFactory register_HelloWorldContext(
    CONTEXT_FACTORY(HelloWorldHttpContext),
    ROOT_FACTORY(HelloWorldRootContext));
// [END serviceextensions_plugin_hello_world]
