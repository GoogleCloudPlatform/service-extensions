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
        ::testing::Values("samples/config_denylist/plugin_cpp.wasm",
                          "samples/config_denylist/plugin_rust.wasm")));

TEST_P(HttpTest, NoConfig) {
  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Send request with bad token. Expect to be denied.
  auto res = http_context.SendRequestHeaders({{"User-Token", "bad-user"}});
  EXPECT_EQ(res.http_code, 0);
  EXPECT_THAT(res.headers, ElementsAre(Pair("User-Token", "bad-user")));
}

TEST_P(HttpTest, RunPlugin) {
  std::string config = R"(
no-user
bad-user
evil-user
  )";

  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path(), config).ok());
  EXPECT_TRUE(root()->isLogged("Config keys size 3"));

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Send request with normal token. Expect to be allowed through.
  auto res1 = http_context.SendRequestHeaders({{"User-Token", "good-user"}});
  EXPECT_EQ(res1.http_code, 0);
  EXPECT_THAT(res1.headers, ElementsAre(Pair("User-Token", "good-user")));

  // Send request with bad token. Expect to be denied.
  auto res2 = http_context.SendRequestHeaders({{"User-Token", "bad-user"}});
  EXPECT_EQ(res2.http_code, 403);
  EXPECT_EQ(res2.body, "Access forbidden.\n");
  EXPECT_THAT(res2.headers, ElementsAre());

  // Send request with no token. Expect to be denied.
  auto res3 = http_context.SendRequestHeaders({});
  EXPECT_EQ(res3.http_code, 403);
  EXPECT_EQ(res3.body, "Access forbidden - token missing.\n");
  EXPECT_THAT(res3.headers, ElementsAre());

  EXPECT_FALSE(handle_->wasm()->isFailed());
}

}  // namespace service_extensions_samples
