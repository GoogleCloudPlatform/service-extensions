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
using ::testing::Pair;

namespace service_extensions_samples {

INSTANTIATE_TEST_SUITE_P(
    EnginesAndPlugins, HttpTest,
    ::testing::Combine(
        ::testing::ValuesIn(proxy_wasm::getWasmEngines()),
        ::testing::Values("samples/block_requests/plugin_cpp.wasm",
                          "samples/block_requests/plugin_rust.wasm")));

TEST_P(HttpTest, RunPlugin) {
  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Send request with no referer. Expect nothing.
  auto res1 = http_context.SendRequestHeaders({});
  EXPECT_EQ(res1.http_code, 0);
  EXPECT_THAT(res1.headers, ElementsAre());

  // Send request with referer with a valid value.
  auto res2 = http_context.SendRequestHeaders({{"Referer", "https://www.google.com/"}});
  EXPECT_EQ(res2.http_code, 0);
  EXPECT_THAT(res2.headers, ElementsAre(Pair("Referer", "https://www.google.com/")));

  // Send request with referer set to the forbidden value.
  auto res3 = http_context.SendRequestHeaders({{"Referer", "https://www.example.com/"}});
  EXPECT_EQ(res3.http_code, 404);
  EXPECT_EQ(res3.body, "Error - Not Found.\n");
  EXPECT_THAT(res3.headers, ElementsAre());

  EXPECT_FALSE(handle_->wasm()->isFailed());
}

}  // namespace service_extensions_samples
