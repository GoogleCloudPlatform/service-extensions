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
        ::testing::Values("samples/noop_logs/plugin_cpp.wasm",
                          "samples/noop_logs/plugin_rust.wasm")));

TEST_P(HttpTest, RunPlugin) {
  // NOTE: This test should use mocks to verify logging order and counts.

  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());
  EXPECT_TRUE(root()->isLogged("root onCreate called"));
  EXPECT_TRUE(root()->isLogged("root onStart called"));
  EXPECT_TRUE(root()->isLogged("root onConfigure called"));

  {
    // Create stream context.
    auto http_context = std::make_unique<TestHttpContext>(handle_);
    EXPECT_TRUE(http_context->isLogged("http onCreate called"));

    // Send request. Expect header.
    auto res1 = http_context->SendRequestHeaders({});
    EXPECT_TRUE(http_context->isLogged("http onRequestHeaders called"));

    // Send response. Expect nothing.
    auto res2 = http_context->SendResponseHeaders({});
    EXPECT_TRUE(http_context->isLogged("http onResponseHeaders called"));
  }
  // Stream cleaned up.
  EXPECT_TRUE(TestContext::isGlobalLogged("http onDone called"));
  EXPECT_TRUE(TestContext::isGlobalLogged("http onDelete called"));

  EXPECT_FALSE(handle_->wasm()->isFailed());

  handle_.reset();
  EXPECT_TRUE(TestContext::isGlobalLogged("root onDone called"));
  EXPECT_TRUE(TestContext::isGlobalLogged("root onDelete called"));
}

}  // namespace service_extensions_samples
