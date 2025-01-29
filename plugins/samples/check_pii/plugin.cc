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
    // Credit card numbers in a 16-digit hyphenated format.
    // Compile the regex expression at plugin setup time, so that this expensive
    // operation is only performed once, and not repeated with each request.
    card_matcher_.emplace("\\d{4}-\\d{4}-\\d{4}-(\\d{4})");

    // Compile the regex for 10-digit numeric codes.
    code10_matcher_.emplace("\\d{7}(\\d{3})");

    // Ensure both regex patterns compiled successfully.
    return card_matcher_->ok() && code10_matcher_->ok();
  }

  const re2::RE2& card_matcher() const { return *card_matcher_; }
  const re2::RE2& code10_matcher() const { return *code10_matcher_; }

  private:
    std::optional<re2::RE2> card_matcher_;
    std::optional<re2::RE2> code10_matcher_;
};

// Checks the response HTTP headers and the response body for the presence of
// credit card numbers and 10-digit numeric codes. Masks the initial numbers
// found while preserving the last few digits for both types of PII.
//
// - Credit Card Numbers: Masks the first 12 digits, displaying only the last 4 digits
//   in the format XXXX-XXXX-XXXX-1234.
// - 10-Digit Codes: Masks the first 7 digits, displaying only the last 3 digits
//   as XXXXXXX123.
//
// Note that for illustrative purposes, this example is kept simple and does not
// handle cases where PII is split across multiple onResponseBody() calls.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<MyRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                         bool end_of_stream) override {
      // One current limitation is that this plugin won't strip PII as intended if the server response is compressed,
      // since in that case the bytes returned by getBufferBytes() will be compressed rather than plaintext data.
      // The simplest workaround is to disallow the server from using response compression.
      // This is achieved by setting "Accept-Encoding: identity" in request headers.
      replaceRequestHeader("accept-encoding", "identity");
      return FilterHeadersStatus::Continue;
    }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    const auto result = getResponseHeaderPairs();
    const auto orig_pairs = result->pairs();

    HeaderStringPairs new_headers;
    bool changed = false;

    for (auto& [k, v] : orig_pairs) {
      std::string key(k.data(), k.size());
      std::string value(v.data(), v.size()); // mutable copy
      changed = maskPII(value) || changed;
      new_headers.emplace_back(key, value);
    }
    if (changed) {
      setResponseHeaderPairs(new_headers);
    }
    return FilterHeadersStatus::Continue;
  }

  FilterDataStatus onResponseBody(size_t body_buffer_length,
                                  bool end_of_stream) override {

    const auto body = getBufferBytes(WasmBufferType::HttpResponseBody, 0,
                                     body_buffer_length);
    std::string body_string = body->toString();  // mutable copy
    if (maskPII(body_string)) {
      setBuffer(WasmBufferType::HttpResponseBody, 0, body_buffer_length,
                body_string);
    }
    return FilterDataStatus::Continue;
  }

 private:
  const MyRootContext* root_;

  bool maskPII(std::string& value) {
    bool modified = false;

    // Mask credit card numbers: XXXX-XXXX-XXXX-1234
    if (re2::RE2::GlobalReplace(&value, root_->card_matcher(),
                                 "XXXX-XXXX-XXXX-\\1") > 0) {
      modified = true;
    }

    // Mask 10-digit codes: XXXXXXX123
    if (re2::RE2::GlobalReplace(&value, root_->code10_matcher(),
                                 "XXXXXXX\\1") > 0) {
      modified = true;
    }

    return modified;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_check_pii]
