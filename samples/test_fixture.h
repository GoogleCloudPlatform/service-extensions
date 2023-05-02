#include "absl/status/status.h"
#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "include/proxy-wasm/exports.h"
#include "include/proxy-wasm/wasm.h"
#include "test/utility.h"

namespace service_extensions_samples {

// TestContext is GCP-like ProxyWasm context (shared for VM + Root + Stream).
//
// NOTE: the base class implements log + get_current_time. This derived class
// primarily implements plugin configuration.
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
      proxy_wasm::WasmBufferType type) override {
    // Provide plugin configuration only.
    if (type == proxy_wasm::WasmBufferType::PluginConfiguration) {
      return &plugin_config_;
    }
    return nullptr;
  }
  // --- END Wasm facing API ---

 private:
  proxy_wasm::BufferBase plugin_config_;
};

// TestStreamContext is GCP-like ProxyWasm Stream context.
// It primarily implements HTTP methods usable by Wasm.
class TestStreamContext : public TestContext {
 public:
  TestStreamContext(std::shared_ptr<proxy_wasm::PluginHandleBase> plugin_handle)
      : TestContext(plugin_handle->wasm().get(),
                    plugin_handle->wasm()
                        ->getRootContext(plugin_handle->plugin(),
                                         /*allow_closed=*/false)
                        ->id(),
                    plugin_handle) {
    this->onCreate();
  }
  ~TestStreamContext() override {
    this->onDone();    // calls wasm if VM not failed
    this->onDelete();  // calls wasm if VM not failed and create succeeded
  }

  // --- BEGIN Wasm facing API ---
  /*
  proxy_wasm::WasmResult getHeaderMapSize(proxy_wasm::WasmHeaderMapType type,
                                          uint32_t* result) override;

  proxy_wasm::WasmResult addHeaderMapValue(proxy_wasm::WasmHeaderMapType type,
                                           std::string_view key,
                                           std::string_view value) override;
  proxy_wasm::WasmResult replaceHeaderMapValue(
      proxy_wasm::WasmHeaderMapType type, std::string_view key,
      std::string_view value) override;
  proxy_wasm::WasmResult removeHeaderMapValue(
      proxy_wasm::WasmHeaderMapType type, std::string_view key) override;
  proxy_wasm::WasmResult getHeaderMapValue(proxy_wasm::WasmHeaderMapType type,
                                           std::string_view key,
                                           std::string_view* value) override;
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
  */
  // --- END Wasm facing API ---
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

  // Load a plugin into the vm_.
  absl::Status CreatePlugin(const std::string& engine,
                            const std::string& wasm_path,
                            const std::string& plugin_config = "");

 protected:
  std::shared_ptr<proxy_wasm::PluginHandleBase> handle_;

 private:
  std::string ReadDataFile(const std::string& path);
};

}  // namespace service_extensions_samples
