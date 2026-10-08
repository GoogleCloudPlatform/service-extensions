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

// [START serviceextensions_plugin_example_testing]
#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    LOG_DEBUG(std::string("request headers ") + std::to_string(id()));

    // Emit headers to logs for debugging.
    /*
    auto result = getRequestHeaderPairs();
    auto pairs = result->pairs();
    LOG_INFO(std::string("num headers: ") + std::to_string(pairs.size()));
    for (auto& p : pairs) {
      LOG_INFO(std::string(p.first) + " -> " + std::string(p.second));
    }
    */
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    LOG_DEBUG(std::string("response headers ") + std::to_string(id()));

    // Emit headers to logs for debugging.
    /*
    auto result = getResponseHeaderPairs();
    auto pairs = result->pairs();
    LOG_INFO(std::string("num headers: ") + std::to_string(pairs.size()));
    for (auto& p : pairs) {
      LOG_INFO(std::string(p.first) + " -> " + std::string(p.second));
    }
    */

    // Emit some timestamps.
    for (int i = 1; i <= 3; ++i) {
      using namespace std::chrono_literals;
      const auto ts = std::chrono::high_resolution_clock::now();
      const auto ns = ts.time_since_epoch() / 1ns;
      LOG_INFO("time " + std::to_string(i) + ": " + std::to_string(ns));
    }

    // Conditionally reply with an error.
    if (getResponseHeader("reply-with-error")->data()) {
      sendLocalResponse(500, "extra", "fake error", {{"error", "goaway"}});
      return FilterHeadersStatus::StopAllIterationAndWatermark;
    }
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_example_testing]
