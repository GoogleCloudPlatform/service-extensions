#include "test_fixture.h"

namespace service_extensions_samples {

proxy_wasm::BufferInterface* TestContext::getBuffer(
    proxy_wasm::WasmBufferType type) {
  // Provide plugin configuration only.
  if (type == proxy_wasm::WasmBufferType::PluginConfiguration) {
    return &plugin_config_;
  }
  return nullptr;
}

proxy_wasm::WasmResult TestStreamContext::getHeaderMapSize(
    proxy_wasm::WasmHeaderMapType type, uint32_t* result) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  *result = result_.headers.size();
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestStreamContext::getHeaderMapValue(
    proxy_wasm::WasmHeaderMapType type, std::string_view key,
    std::string_view* value) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  auto it = result_.headers.find(std::string(key));
  if (it == result_.headers.end()) {
    return proxy_wasm::WasmResult::NotFound;
  }
  *value = it->second;
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestStreamContext::addHeaderMapValue(
    proxy_wasm::WasmHeaderMapType type, std::string_view key,
    std::string_view value) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  auto& val = result_.headers[std::string(key)];
  if (val.empty()) {
    val = std::string(value);
  } else {
    val = absl::StrCat(val, ", ", value);  // RFC 9110 Field Order
  }
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestStreamContext::replaceHeaderMapValue(
    proxy_wasm::WasmHeaderMapType type, std::string_view key,
    std::string_view value) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  result_.headers[std::string(key)] = std::string(value);
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestStreamContext::removeHeaderMapValue(
    proxy_wasm::WasmHeaderMapType type, std::string_view key) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  result_.headers.erase(std::string(key));
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestStreamContext::getHeaderMapPairs(
    proxy_wasm::WasmHeaderMapType type, proxy_wasm::Pairs* result) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  for (const auto& [key, val] : result_.headers) {
    result->push_back({key, val});
  }
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestStreamContext::setHeaderMapPairs(
    proxy_wasm::WasmHeaderMapType type, const proxy_wasm::Pairs& pairs) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  result_.headers.clear();
  for (const auto& [key, val] : pairs) {
    addHeaderMapValue(type, key, val);
  }
  return proxy_wasm::WasmResult::Ok;
}

proxy_wasm::WasmResult TestStreamContext::sendLocalResponse(
    uint32_t response_code, std::string_view body_text,
    proxy_wasm::Pairs additional_headers, uint32_t grpc_status,
    std::string_view details) {
  if (phase_ != proxy_wasm::WasmHeaderMapType::RequestHeaders &&
      phase_ != proxy_wasm::WasmHeaderMapType::ResponseHeaders) {
    return proxy_wasm::WasmResult::BadArgument;
  }
  result_.http_code = response_code;
  result_.body = body_text;
  result_.grpc_code = grpc_status;
  result_.details = details;
  for (const auto& [key, val] : additional_headers) {
    result_.headers[std::string(key)] = std::string(val);
  }
  return proxy_wasm::WasmResult::Ok;
}

TestStreamContext::Result TestStreamContext::SendRequestHeaders(
    TestStreamContext::Headers headers) {
  result_ = Result{.headers = std::move(headers)};
  phase_ = proxy_wasm::WasmHeaderMapType::RequestHeaders;
  result_.status =
      onRequestHeaders(result_.headers.size(), /*end_of_stream=*/false);
  phase_ = proxy_wasm::WasmHeaderMapType(-1);  // ideally 0 would mean unset
  return std::move(result_);
}
TestStreamContext::Result TestStreamContext::SendResponseHeaders(
    TestStreamContext::Headers headers) {
  result_ = Result{.headers = std::move(headers)};
  phase_ = proxy_wasm::WasmHeaderMapType::ResponseHeaders;
  result_.status =
      onResponseHeaders(result_.headers.size(), /*end_of_stream=*/false);
  phase_ = proxy_wasm::WasmHeaderMapType(-1);  // ideally 0 would mean unset
  return std::move(result_);
}

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
