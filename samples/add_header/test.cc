#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "include/proxy-wasm/exports.h"
#include "include/proxy-wasm/wasm.h"
#include "samples/test_fixture.h"

namespace service_extensions_samples {

INSTANTIATE_TEST_SUITE_P(
    EnginesAndPlugins, HttpTest,
    ::testing::Combine(::testing::ValuesIn(proxy_wasm::getWasmEngines()),
                       ::testing::Values("samples/add_header/plugin_cpp.wasm",
                                         "samples/add_header/plugin_rust.wasm")));

TEST_P(HttpTest, RunPlugin) {
  // Create VM + load plugin.
  ASSERT_TRUE(CreatePlugin(engine(), path(), "TODO config").ok());

  // Create stream.
  auto stream_context = std::make_unique<TestStreamContext>(handle_);

  // assert/expect not failed
  stream_context->onRequestHeaders(/*request_header_->NumHeaders()*/ 0,
                                   /*end_of_stream=*/false);
  stream_context->onResponseHeaders(/*request_header_->NumHeaders()*/ 0,
                                    /*end_of_stream=*/false);

  EXPECT_FALSE(handle_->wasm()->isFailed());

  // check failure
  // auto *integration = dynamic_cast<TestIntegration
  // *>(plugin->wasm()->wasm_vm()->integration().get());
  // ASSERT_TRUE(integration->isErrorLogged(
}

}  // namespace service_extensions_samples
