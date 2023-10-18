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

REGISTER_TESTS(HttpTest);

TEST_P(HttpTest, RunPluginNoPathHeader) {
  // Create VM and load the plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  auto res = http_context.SendRequestHeaders({});
  EXPECT_EQ(res.http_code, 0);
  EXPECT_FALSE(handle_->wasm()->isFailed());
}

TEST_P(HttpTest, RunPluginNoToken) {
  // Create VM and load the plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  auto res = http_context.SendRequestHeaders(
      {{":path", "/foo?bar=baz&a=b"}});
  EXPECT_TRUE(http_context.isLogged("token: <missing>"));
  EXPECT_EQ(res.http_code, 0);
  EXPECT_FALSE(handle_->wasm()->isFailed());
}

TEST_P(HttpTest, RunPluginLogToken) {
  // Create VM and load the plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  auto res = http_context.SendRequestHeaders(
      {{":path", "/foo?bar=baz&token=so\%20special&a=b"}});
  EXPECT_TRUE(http_context.isLogged("token: so special"));
  EXPECT_EQ(res.http_code, 0);
  EXPECT_FALSE(handle_->wasm()->isFailed());
}

}  // namespace service_extensions_samples
