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
        ::testing::Values("samples/http_redirect/plugin_cpp.wasm",
                          "samples/http_redirect/plugin_rust.wasm")));

TEST_P(HttpTest, RunPlugin) {
  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream context.
  auto http_context = TestHttpContext(handle_);

  // Expect no-op if no path is specified. (Never expected.)
  auto res = http_context.SendRequestHeaders({});
  EXPECT_EQ(res.http_code, 0);

  // Send request with non-matching path. We have to supply the ":path"
  // pseudo-header even though Envoy will do it automatically in production:
  // https://github.com/GoogleCloudPlatform/service-extensions-samples/issues/10
  auto res1 = http_context.SendRequestHeaders({{":path", "/"}});
  EXPECT_EQ(res1.http_code, 0);

  // Send request with matching path, expect redirect.
  auto res2 = http_context.SendRequestHeaders({{":path", "/index.php"}});
  EXPECT_EQ(res2.http_code, 301);
  EXPECT_THAT(res2.headers,
              ElementsAre(Pair("Location", "http://www.example.com/")));

  EXPECT_FALSE(handle_->wasm()->isFailed());
}

}  // namespace service_extensions_samples
