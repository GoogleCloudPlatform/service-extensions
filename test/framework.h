/*
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "absl/status/status.h"
#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "include/proxy-wasm/exports.h"
#include "include/proxy-wasm/wasm.h"
#include "test/utility.h"

namespace service_extensions_samples {

// TestContext is GCP-like ProxyWasm context (shared for VM + Root + Stream).
//
// NOTE: the base class implements logging. This derived class primarily
// implements serving plugin configuration.
class TestContext : public proxy_wasm::TestContext {
 public:
  // VM Context constructor.
  TestContext(proxy_wasm::WasmBase* wasm) : proxy_wasm::TestContext(wasm) {
    // No plugin config in VM context.
  }
  // Root Context constructor.
  TestContext(proxy_wasm::WasmBase* wasm,
              std::shared_ptr<proxy_wasm::PluginBase> plugin)
      : proxy_wasm::TestContext(wasm, plugin) {
    plugin_config_.set(plugin_->plugin_configuration_);
  }
  // Stream Context constructor.
  TestContext(proxy_wasm::WasmBase* wasm, uint32_t parent_context_id,
              std::shared_ptr<proxy_wasm::PluginHandleBase> plugin_handle)
      : proxy_wasm::TestContext(wasm, parent_context_id, plugin_handle) {
    plugin_config_.set(plugin_->plugin_configuration_);
  }
  virtual ~TestContext() = default;

  // Not copyable or movable.
  TestContext(const TestContext&) = delete;
  TestContext& operator=(const TestContext&) = delete;

  // --- BEGIN Wasm facing API ---
  proxy_wasm::BufferInterface* getBuffer(
      proxy_wasm::WasmBufferType type) override;
  uint64_t getCurrentTimeNanoseconds() override;
  uint64_t getMonotonicTimeNanoseconds() override;
  proxy_wasm::WasmResult log(uint32_t log_level,
                             std::string_view message) override;
  // --- END Wasm facing API ---

 private:
  proxy_wasm::BufferBase plugin_config_;
};

// TestHttpContext is a GCP-like ProxyWasm Stream context. It primarily
// implements HTTP methods usable by Wasm.
//
// The implementation is an incomplete test-only approximation of HTTP-compliant
// header handling. It's missing at least the following:
// - case insensitivity
// - cookie handling
// - restricted header checks
// - empty value checks
// - size checks
class TestHttpContext : public TestContext {
 public:
  TestHttpContext(std::shared_ptr<proxy_wasm::PluginHandleBase> plugin_handle)
      : TestContext(plugin_handle->wasm().get(),
                    plugin_handle->wasm()
                        ->getRootContext(plugin_handle->plugin(),
                                         /*allow_closed=*/false)
                        ->id(),
                    plugin_handle) {
    this->onCreate();
  }
  ~TestHttpContext() override {
    this->onDone();    // calls wasm if VM not failed
    this->onDelete();  // calls wasm if VM not failed and create succeeded
  }

  // --- BEGIN Wasm facing API ---
  proxy_wasm::WasmResult getHeaderMapSize(proxy_wasm::WasmHeaderMapType type,
                                          uint32_t* result) override;
  proxy_wasm::WasmResult getHeaderMapValue(proxy_wasm::WasmHeaderMapType type,
                                           std::string_view key,
                                           std::string_view* value) override;
  proxy_wasm::WasmResult addHeaderMapValue(proxy_wasm::WasmHeaderMapType type,
                                           std::string_view key,
                                           std::string_view value) override;
  proxy_wasm::WasmResult replaceHeaderMapValue(
      proxy_wasm::WasmHeaderMapType type, std::string_view key,
      std::string_view value) override;
  proxy_wasm::WasmResult removeHeaderMapValue(
      proxy_wasm::WasmHeaderMapType type, std::string_view key) override;
  proxy_wasm::WasmResult getHeaderMapPairs(proxy_wasm::WasmHeaderMapType type,
                                           proxy_wasm::Pairs* result) override;
  proxy_wasm::WasmResult setHeaderMapPairs(
      proxy_wasm::WasmHeaderMapType type,
      const proxy_wasm::Pairs& pairs) override;

  proxy_wasm::WasmResult sendLocalResponse(uint32_t response_code,
                                           std::string_view body_text,
                                           proxy_wasm::Pairs additional_headers,
                                           uint32_t grpc_status,
                                           std::string_view details) override;
  // --- END Wasm facing API ---

  // Testing types. Optimized for ease of use not performance.
  using Headers = std::map<std::string, std::string>;  // key-sorted map
  struct Result {
    // Filter status returned by handler.
    proxy_wasm::FilterHeadersStatus status;
    // Mutated headers, also used for local response.
    Headers headers = {};
    // Local response, sent to user via proxy.
    uint32_t http_code = 0;
    std::string body = "";
    // Local response, sent to proxy.
    uint32_t grpc_code = 0;
    std::string details = "";
  };

  // Testing helpers. Use these instead of direct on*Headers methods.
  Result SendRequestHeaders(Headers headers);
  Result SendResponseHeaders(Headers headers);

 private:
  // State tracked during a headers call. Invalid otherwise.
  proxy_wasm::WasmHeaderMapType phase_;
  Result result_;
};

// TestWasm is a light wrapper enabling custom TestContext.
// TODO set allowed_capabilities
class TestWasm : public proxy_wasm::WasmBase {
 public:
  TestWasm(std::unique_ptr<proxy_wasm::WasmVm> vm)
      : proxy_wasm::WasmBase(std::move(vm), /*vm_id=*/"",
                             /*vm_configuration=*/"",
                             /*vm_key=*/"", /*envs=*/{},
                             /*allowed_capabilities=*/{}) {}

  TestWasm(const std::shared_ptr<proxy_wasm::WasmHandleBase>& base_wasm_handle,
           const proxy_wasm::WasmVmFactory& factory)
      : proxy_wasm::WasmBase(base_wasm_handle, factory) {}

  proxy_wasm::ContextBase* createVmContext() override {
    return new TestContext(this);
  };

  proxy_wasm::ContextBase* createRootContext(
      const std::shared_ptr<proxy_wasm::PluginBase>& plugin) override {
    return new TestContext(this, plugin);
  }
};

// HttpTest is the actual test fixture.
// It is parameterized by a tuple of {engine, wasm-path}.
class HttpTest
    : public testing::TestWithParam<std::tuple<std::string, std::string>> {
 public:
  HttpTest() {
    std::cout << "Running " << engine() << ": " << path() << std::endl;
  }

  std::string engine() { return std::get<0>(GetParam()); }
  std::string path() { return std::get<1>(GetParam()); }

 protected:
  // Load VM and plugin and set these into the handle_ variable.
  absl::Status CreatePlugin(const std::string& engine,
                            const std::string& wasm_path,
                            const std::string& plugin_config = "");

  TestContext* root() {
    if (!handle_) return nullptr;
    return static_cast<TestContext*>(
        handle_->wasm()->getRootContext(handle_->plugin(),
                                        /*allow_closed=*/false));
  }

  std::shared_ptr<proxy_wasm::PluginHandleBase> handle_;

 private:
  std::string ReadDataFile(const std::string& path);
};

}  // namespace service_extensions_samples
