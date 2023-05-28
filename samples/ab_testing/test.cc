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

#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "include/proxy-wasm/exports.h"
#include "include/proxy-wasm/wasm.h"
#include "test/framework.h"

using ::testing::ElementsAre;
using ::testing::IsSubsetOf;
using ::testing::Pair;

namespace service_extensions_samples {

INSTANTIATE_TEST_SUITE_P(
    EnginesAndPlugins, HttpTest,
    ::testing::Combine(
        ::testing::ValuesIn(proxy_wasm::getWasmEngines()),
        ::testing::Values("samples/ab_testing/plugin_cpp.wasm")));

TEST_P(HttpTest, UnrelatedPathUnchanged) {
  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Send a request that is irrelevant to the A/B experiment. Expect the path to stay unchanged.
  auto res1 = http_context.SendRequestHeaders({{":path", "example.com/123"}});
  EXPECT_EQ(res1.http_code, 0);
  EXPECT_THAT(res1.headers, ElementsAre(Pair(":path", "example.com/123")));

  EXPECT_FALSE(handle_->wasm()->isFailed());
}

TEST_P(HttpTest, ExperimentPathExercised) {
  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Send requests relevant to the experiment until both branches are exercised.
  bool file1_served = false;
  bool file2_served = false;
  while (!file1_served || !file2_served) {
    auto res = http_context.SendRequestHeaders({{":path", "example.com/file1.blah"}});
    EXPECT_EQ(res.http_code, 0);
    std::string path = res.headers[":path"];
    if (path == "example.com/file1.blah") {
      EXPECT_THAT(res.headers, ElementsAre(Pair(":path", "example.com/file1.blah")));
      file1_served = true;
    } else {
      EXPECT_THAT(res.headers, ElementsAre(Pair(":path", "example.com/file2.blah")));
      file2_served = true;
    }
  }

  EXPECT_FALSE(handle_->wasm()->isFailed());
}

}  // namespace service_extensions_samples
