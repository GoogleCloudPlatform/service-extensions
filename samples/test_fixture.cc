#include "test_fixture.h"

namespace service_extensions_samples {

absl::Status HttpTest::CreatePlugin(const std::string& engine,
                                    const std::string& wasm_path,
                                    const std::string& plugin_config) {
  // Read the wasm source.
  std::string wasm_module = ReadDataFile(wasm_path);

  // Create a VM and load the plugin.
  auto vm = proxy_wasm::TestVm::MakeVm(engine);
  auto wasm = std::make_shared<TestWasm>(std::move(vm));
  if (!wasm->load(wasm_module, /*allow_precompiled=*/false)) {
    absl::string_view err = "Failed to load Wasm code";
    wasm->fail(proxy_wasm::FailState::UnableToInitializeCode, err);
    return absl::FailedPreconditionError(err);
  }
  if (!wasm->initialize()) {
    absl::string_view err = "Failed to initialize Wasm code";
    wasm->fail(proxy_wasm::FailState::UnableToInitializeCode, err);
    return absl::FailedPreconditionError(err);
  }

  // Create a plugin.
  const auto plugin = std::make_shared<proxy_wasm::PluginBase>(
      /*name=*/"test", /*root_id=*/"", /*vm_id=*/"",
      /*engine=*/wasm->wasm_vm()->getEngineName(), plugin_config,
      /*fail_open=*/false, /*key=*/"");

  // Create root context, call onStart().
  proxy_wasm::ContextBase* root_context = wasm->start(plugin);
  if (root_context == nullptr) {
    return absl::FailedPreconditionError("Plugin.start failed");
  }

  // On the root context, call onConfigure().
  if (!wasm->configure(root_context, plugin)) {
    return absl::FailedPreconditionError("Plugin.configure failed");
  }

  // Store pointers in handle_ property.
  handle_ = std::make_shared<proxy_wasm::PluginHandleBase>(
      std::make_shared<proxy_wasm::WasmHandleBase>(wasm), plugin);

  return absl::OkStatus();
}

std::string HttpTest::ReadDataFile(const std::string& path) {
  std::ifstream file(path, std::ios::binary);
  EXPECT_FALSE(file.fail()) << "failed to open: " << path;
  std::stringstream file_string_stream;
  file_string_stream << file.rdbuf();
  return file_string_stream.str();
}

}  // namespace service_extensions_samples
