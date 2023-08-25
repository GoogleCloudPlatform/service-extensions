// Copyright 2023 Google LLC
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

#include <unordered_set>

#include "proxy_wasm_intrinsics.h"
#include "absl/strings/str_cat.h"

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t config_len) override {
    // Fetch plugin config and take ownership of the buffer.
    config_ =
        getBufferBytes(WasmBufferType::PluginConfiguration, 0, config_len);

    // Extract string keys without copying data.
    std::string_view config = config_->view();
    size_t idx = 0;
    while (idx < config.size()) {
      size_t nxt = config.find_first_of(" \f\n\r\t\v", idx);
      if (idx != nxt) {
        tokens_.insert(config.substr(idx, nxt - idx));
      }
      if (nxt == std::string_view::npos) {
        break;
      }
      idx = nxt + 1;
    }
    LOG_INFO(absl::StrCat("Config keys size ", tokens_.size()));
    return true;
  }

  const std::unordered_set<std::string_view>& tokens() { return tokens_; }

 private:
  WasmDataPtr config_;
  std::unordered_set<std::string_view> tokens_;
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root),
        tokens_(static_cast<MyRootContext*>(root)->tokens()) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    WasmDataPtr token = getRequestHeader("User-Token");
    if (!token || token->size() == 0) {
      sendLocalResponse(403, "", "Access forbidden - token missing.\n", {});
      return FilterHeadersStatus::StopAllIterationAndWatermark;
    }
    if (tokens_.count(token->view()) > 0) {
      sendLocalResponse(403, "", "Access forbidden.\n", {});
      return FilterHeadersStatus::StopAllIterationAndWatermark;
    }
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    return FilterHeadersStatus::Continue;
  }

 private:
  const std::unordered_set<std::string_view>& tokens_;
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
