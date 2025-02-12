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

// [START serviceextensions_plugin_configurable_body_modification]
#include "absl/strings/numbers.h"
#include "absl/strings/str_format.h"
#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Check request headers for modifications to be made to request body
    WasmDataPtr request_body_start =
        getRequestHeader("Modify-Request-Body-Start");
    WasmDataPtr request_body_length =
        getRequestHeader("Modify-Request-Body-Length");
    WasmDataPtr request_body_data =
        getRequestHeader("Modify-Request-Body-Data");
    if (!request_body_start->view().empty()) {
      size_t start;
      if (absl::SimpleAtoi(request_body_start->toString(), &start)) {
        request_body_modifications_.start = start;
      } else {
        sendLocalResponse(
            400,
            absl::StrFormat("Invalid Modify-Request-Body-Start: %s",
                            request_body_start->toString()),
            "", {});
      }
    }
    if (!request_body_length->view().empty()) {
      size_t length;
      if (absl::SimpleAtoi(request_body_length->toString(), &length)) {
        request_body_modifications_.length = length;
      } else {
        sendLocalResponse(
            400,
            absl::StrFormat("Invalid Modify-Request-Body-Length: %s",
                            request_body_length->toString()),
            "", {});
      }
    }
    if (!request_body_data->view().empty()) {
      request_body_modifications_.data = request_body_data->view();
    }
    // Check request headers for modifications to be made to response body
    WasmDataPtr response_body_start =
        getRequestHeader("Modify-Response-Body-Start");
    WasmDataPtr response_body_length =
        getRequestHeader("Modify-Response-Body-Length");
    WasmDataPtr response_body_data =
        getRequestHeader("Modify-Response-Body-Data");
    if (!response_body_start->view().empty()) {
      size_t start;
      if (absl::SimpleAtoi(response_body_start->toString(), &start)) {
        response_body_modifications_.start = start;
      } else {
        sendLocalResponse(
            400,
            absl::StrFormat("Invalid Modify-Response-Body-Start: %s",
                            response_body_start->toString()),
            "", {});
      }
    }
    if (!response_body_length->view().empty()) {
      size_t length;
      if (absl::SimpleAtoi(response_body_length->toString(), &length)) {
        response_body_modifications_.length = length;
      } else {
        sendLocalResponse(
            400,
            absl::StrFormat("Invalid Modify-Response-Body-Length: %s",
                            response_body_length->toString()),
            "", {});
      }
    }
    if (!response_body_data->view().empty()) {
      response_body_modifications_.data = response_body_data->view();
    }
    return FilterHeadersStatus::Continue;
  }

  FilterDataStatus onRequestBody(size_t body_length,
                                 bool end_of_stream) override {
    if (setBuffer(WasmBufferType::HttpRequestBody,
                  request_body_modifications_.start,
                  request_body_modifications_.length,
                  request_body_modifications_.data) != WasmResult::Ok) {
      setBuffer(WasmBufferType::HttpRequestBody, 0, body_length,
                "failed setBuffer");
    }
    return FilterDataStatus::Continue;
  }

  FilterDataStatus onResponseBody(size_t body_length,
                                  bool end_of_stream) override {
    if (setBuffer(WasmBufferType::HttpResponseBody,
                  response_body_modifications_.start,
                  response_body_modifications_.length,
                  response_body_modifications_.data) != WasmResult::Ok) {
      setBuffer(WasmBufferType::HttpResponseBody, 0, body_length,
                "failed setBuffer");
    }
    return FilterDataStatus::Continue;
  }

 private:
  // Store modifications in HttpContext to be accessed in body callbacks.
  struct BodyModificationsParams {
    size_t start = 0;
    size_t length = 0;
    std::string data = "";
  };
  BodyModificationsParams request_body_modifications_;
  BodyModificationsParams response_body_modifications_;
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_configurable_body_modification]
