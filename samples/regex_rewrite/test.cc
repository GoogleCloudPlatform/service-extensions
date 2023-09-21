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

REGISTER_TESTS(HttpTest);

TEST_P(HttpTest, NoMatch) {
  // Create VM and load the plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Expect no matches, so no changes.
  auto res =
      http_context.SendRequestHeaders({{":path", "/one/two?three=four"}});
  EXPECT_EQ(res.http_code, 0);
  EXPECT_THAT(res.headers, ElementsAre(Pair(":path", "/one/two?three=four")));

  EXPECT_FALSE(handle_->wasm()->isFailed());
}

TEST_P(HttpTest, MatchAndReplace) {
  // Create VM and load the plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Expect the plugin to replace the first "foo-" path fragment.
  auto res = http_context.SendRequestHeaders(
      {{":path", "/pre/foo-one/foo-two/post?a=b"}});
  EXPECT_EQ(res.http_code, 0);
  EXPECT_THAT(res.headers,
              ElementsAre(Pair(":path", "/pre/one/foo-two/post?a=b")));

  EXPECT_FALSE(handle_->wasm()->isFailed());
}

static void BM_MatchAndReplace(benchmark::State& state,
                               const std::string& engine,
                               const std::string& path) {
  auto plugin = *CreateProxyWasmPlugin(engine, path);
  auto http_context = TestHttpContext(plugin);
  for (auto _ : state) {
    // The response handler conditionally adds a header.
    http_context.SendRequestHeaders(
        {{":path", "/pre/foo-one/foo-two/post?a=b"}});
  }
}
REGISTER_BENCH(BM_MatchAndReplace);

}  // namespace service_extensions_samples
