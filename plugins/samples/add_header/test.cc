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

#include "benchmark/benchmark.h"
#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "include/proxy-wasm/exports.h"
#include "include/proxy-wasm/wasm.h"
#include "test/framework.h"

using ::testing::ElementsAre;
using ::testing::Pair;

namespace service_extensions_samples {

static void BM_AddHeader(benchmark::State& state, const std::string& engine,
                         const std::string& path) {
  auto plugin = *CreateProxyWasmPlugin(engine, path);
  auto http_context = TestHttpContext(plugin);
  for (auto _ : state) {
    // The request handler blindly adds a header.
    http_context.SendRequestHeaders({{"Message", "foo"}});
  }
}
REGISTER_BENCH(BM_AddHeader);

static void BM_ReadAndAddHeader(benchmark::State& state,
                                const std::string& engine,
                                const std::string& path) {
  auto plugin = *CreateProxyWasmPlugin(engine, path);
  auto http_context = TestHttpContext(plugin);
  for (auto _ : state) {
    // The response handler conditionally adds a header.
    http_context.SendResponseHeaders({{"Message", "foo"}});
  }
}
REGISTER_BENCH(BM_ReadAndAddHeader);

}  // namespace service_extensions_samples
