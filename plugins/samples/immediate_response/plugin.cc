// Copyright 2025 Google LLC
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

// [START serviceextensions_plugin_immediate_response]
#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    addRequestHeader("Greeting", "hello");
    auto immediate_response_request_headers =
        getRequestHeader("Send-Immediate-Response");
    if (immediate_response_request_headers &&
        immediate_response_request_headers->view() == "true") {
      sendLocalResponse(500, "sent immediate response in onRequestHeaders",
                        "Immediate response body",
                        {{"ImmediateResponseHeaderKey", "Value"}});
    }
    addRequestHeader("Farewell", "goodbye");
    return FilterHeadersStatus::Continue;
  }

  FilterDataStatus onRequestBody(size_t body_len, bool end_of_stream) override {
    std::string body =
        getBufferBytes(WasmBufferType::HttpRequestBody, 0, body_len)
            ->toString();
    if (body == "Immediate response in onRequestBody") {
      sendLocalResponse(500, "sent immediate response in onRequestBody",
                        "Immediate response body",
                        {{"ImmediateResponseHeaderKey", "Value"}});
    }
    setBuffer(WasmBufferType::HttpRequestBody, body_len, 0, "foo");
    return FilterDataStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    addResponseHeader("Greeting", "hello");
    auto immediate_response_response_headers =
        getResponseHeader("Send-Immediate-Response");
    if (immediate_response_response_headers &&
        immediate_response_response_headers->view() == "true") {
      sendLocalResponse(500, "sent immediate response in onResponseHeaders",
                        "Immediate response body",
                        {{"ImmediateResponseHeaderKey", "Value"}});
    }
    addResponseHeader("Farewell", "goodbye");
    return FilterHeadersStatus::Continue;
  }

  FilterDataStatus onResponseBody(size_t chunk_len,
                                  bool end_of_stream) override {
    setBuffer(WasmBufferType::HttpResponseBody, chunk_len, 0, "bar");
    return FilterDataStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_immediate_response]
