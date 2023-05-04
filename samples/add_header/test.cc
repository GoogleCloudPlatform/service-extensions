#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "include/proxy-wasm/exports.h"
#include "include/proxy-wasm/wasm.h"
#include "samples/test_fixture.h"

using ::testing::ElementsAre;
using ::testing::Pair;

namespace service_extensions_samples {

INSTANTIATE_TEST_SUITE_P(
    EnginesAndPlugins, HttpTest,
    ::testing::Combine(
        ::testing::ValuesIn(proxy_wasm::getWasmEngines()),
        ::testing::Values("samples/add_header/plugin_cpp.wasm",
                          "samples/add_header/plugin_rust.wasm")));

TEST_P(HttpTest, RunPlugin) {
  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path()).ok());

  // Create stream.
  auto stream_context = std::make_unique<TestStreamContext>(handle_);

  // Send request. Expect header.
  auto res1 = stream_context->SendRequestHeaders({});
  EXPECT_EQ(res1.http_code, 0);
  EXPECT_THAT(res1.headers, ElementsAre(Pair("Message", "hello")));
  EXPECT_FALSE(handle_->wasm()->isFailed());

  // Send response. Expect nothing.
  auto res2 = stream_context->SendResponseHeaders({});
  EXPECT_EQ(res2.http_code, 0);
  EXPECT_THAT(res2.headers, ElementsAre());
  EXPECT_FALSE(handle_->wasm()->isFailed());

  // Send response with magic header. Expect addition.
  auto res3 = stream_context->SendResponseHeaders({{"Message", "foo"}});
  EXPECT_EQ(res3.http_code, 0);
  EXPECT_THAT(res3.headers, ElementsAre(Pair("Message", "foo, bar")));
  EXPECT_FALSE(handle_->wasm()->isFailed());
}

}  // namespace service_extensions_samples
