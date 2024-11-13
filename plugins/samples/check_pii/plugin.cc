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

// [START serviceextensions_plugin_check_pii]
#include "proxy_wasm_intrinsics.h"
#include "re2/re2.h"

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t) override {
    // Credit card numbers in a 19 character hyphenated format.
    // Compile the regex expression at plugin setup time.
    card_match.emplace("\\d{4}-\\d{4}-\\d{4}-(\\d{4})");
    return card_match->ok();
  }

  std::optional<re2::RE2> card_match;
};

// Checks the response http headers, and the response body for the presence of
// credit card numbers. Mask the initial numbers case found.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<MyRootContext*>(root)) {}

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    const auto pii_header = getResponseHeader("google-run-pii-check");
    if (pii_header && pii_header->view() == "true") {
      check_body_ = true;
      const auto result = getResponseHeaderPairs();
      const auto pairs = result->pairs();
      for (auto& p : pairs) {
        std::string header_value = std::string(p.second);  // mutable copy
        if (maskCardNumbers(header_value)) {
          replaceResponseHeader(p.first, header_value);
        }
      }
    }
    return FilterHeadersStatus::Continue;
  }

  FilterDataStatus onResponseBody(size_t body_buffer_length,
                                  bool end_of_stream) override {
    if (check_body_) {
      const auto body = getBufferBytes(WasmBufferType::HttpResponseBody, 0,
                                       body_buffer_length);
      std::string body_string = body->toString();  // mutable copy
      if (maskCardNumbers(body_string)) {
        setBuffer(WasmBufferType::HttpResponseBody, 0, body_buffer_length,
                  body_string);
      }
    }
    return FilterDataStatus::Continue;
  }

 private:
  const MyRootContext* root_;
  bool check_body_ = false;

  bool maskCardNumbers(std::string& value) {
    return re2::RE2::GlobalReplace(&value, *root_->card_match,
                                   "XXXX-XXXX-XXXX-\\1") > 0;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_check_pii]
