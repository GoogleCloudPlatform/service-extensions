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

// [START serviceextensions_plugin_lexbor_test]
#include "proxy_wasm_intrinsics.h"
#include "lexbor/html/html.h"


class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  // Add foo onto the end of each request body chunk
  FilterDataStatus onRequestBody(size_t chunk_len,
                                 bool end_of_stream) override {
    const auto body = getBufferBytes(WasmBufferType::HttpRequestBody, 0,
          chunk_len);
    std::string body_string = body->toString();
    return FilterDataStatus::Continue;
  }

  // Add bar onto the end of each response body chunk
  FilterDataStatus onResponseBody(size_t chunk_len,
                                  bool end_of_stream) override {
    setBuffer(WasmBufferType::HttpResponseBody, chunk_len, 0, "bar");
    return FilterDataStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_lexbor_test]


  // FilterDataStatus onRequestBody(size_t chunk_len,
  //                                bool end_of_stream) override {
  //   const auto body = getBufferBytes(WasmBufferType::HttpRequestBody, 0,
  //         chunk_len);
  //   // std::string body_string = body->toString();
  //   // const lxb_char_t body_arr[] = body_string.c_str();
  //   lxb_status_t status;
  //   lxb_html_parser_t *parser;
  //   parser = lxb_html_parser_create();
  //   status = lxb_html_parser_init(parser);
  //   if (status != LXB_STATUS_OK) {
  //       setBuffer(WasmBufferType::HttpRequestBody, chunk_len, 0, "foo");
  //   }
  //   lxb_html_document_t *document = lxb_html_parse(parser, reinterpret_cast<const lxb_char_t*>(body->data()), chunk_len);
  //   auto is_h1_exist = lxb_dom_element_is_set(lxb_dom_interface_element(document->body), (const lxb_char_t *) "h3", 2);
  //   if (is_h1_exist != LXB_STATUS_OK) {
  //       setBuffer(WasmBufferType::HttpRequestBody, chunk_len, 0, "foo");
  //   }
  //   return FilterDataStatus::Continue;
  // }