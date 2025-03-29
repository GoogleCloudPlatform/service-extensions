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

#include "test/framework.h"

#include <boost/dll/runtime_symbol_info.hpp>

#include "absl/strings/str_cat.h"

namespace service_extensions_samples {

size_t Buffer::size() const { return owned_string_buffer_.size(); }
proxy_wasm::WasmResult Buffer::copyTo(proxy_wasm::WasmBase* wasm, size_t start,
                                      size_t length, uint64_t ptr_ptr,
                                      uint64_t size_ptr) const {
  if (start + length > owned_string_buffer_.size()) {
    return proxy_wasm::WasmResult::InvalidMemoryAccess;
  }
  std::string_view s(owned_string_buffer_.data() + start, length);
  if (!wasm->copyToPointerSize(s, ptr_ptr, size_ptr)) {
    return proxy_wasm::WasmResult::InvalidMemoryAccess;
  }
  return proxy_wasm::WasmResult::Ok;
}

proxy_wasm::WasmResult Buffer::copyFrom(size_t start, size_t length,
                                        std::string_view data) {
  if (start > owned_string_buffer_.size()) {
    start = owned_string_buffer_.size();
  }
  owned_string_buffer_.replace(start, length, data);
  return proxy_wasm::WasmResult::Ok;
}

proxy_wasm::BufferInterface* TestContext::getBuffer(
    proxy_wasm::WasmBufferType type) {
  switch (type) {
    case proxy_wasm::WasmBufferType::PluginConfiguration:
      return &plugin_config_;
    default:
      return nullptr;
  }
}

uint64_t TestContext::getCurrentTimeNanoseconds() {
  // Return some frozen timestamp.
  return absl::ToUnixNanos(options().clock_time);
}
uint64_t TestContext::getMonotonicTimeNanoseconds() {
  // Return some frozen timestamp.
  return absl::ToUnixNanos(options().clock_time);
}
proxy_wasm::WasmResult TestContext::log(uint32_t log_level,
                                        std::string_view message) {
  logging_bytes_ += message.size();
  if (wasmVm()->cmpLogLevel(proxy_wasm::LogLevel::trace)) {
    std::cout << "TRACE from testcontext: [log] " << message << std::endl;
  }
  if (wasmVm()->cmpLogLevel(static_cast<proxy_wasm::LogLevel>(log_level))) {
    phase_logs_.emplace_back(message);
    // Optionally log to file.
    if (options().log_file) {
      options().log_file << message << std::endl;
    }
  }
  return proxy_wasm::WasmResult::Ok;
}
ContextOptions& TestContext::options() const {
  return static_cast<TestWasm*>(wasm())->options();
}

proxy_wasm::BufferInterface* TestHttpContext::getBuffer(
    proxy_wasm::WasmBufferType type) {
  switch (type) {
    case proxy_wasm::WasmBufferType::PluginConfiguration:
      return TestContext::getBuffer(type);
    case proxy_wasm::WasmBufferType::HttpRequestBody:
      if (current_callback_ == TestHttpContext::CallbackType::RequestBody) {
        return &body_buffer_;
      }
      break;
    case proxy_wasm::WasmBufferType::HttpResponseBody:
      if (current_callback_ == TestHttpContext::CallbackType::ResponseBody) {
        return &body_buffer_;
      }
      break;
    default:
      return nullptr;
  }
  return nullptr;
}
proxy_wasm::WasmResult TestHttpContext::getHeaderMapSize(
    proxy_wasm::WasmHeaderMapType type, uint32_t* result) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  *result = result_.headers.size();
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestHttpContext::getHeaderMapValue(
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
proxy_wasm::WasmResult TestHttpContext::addHeaderMapValue(
    proxy_wasm::WasmHeaderMapType type, std::string_view key,
    std::string_view value) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  result_.headers.InsertOrAppend(key, value);
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestHttpContext::replaceHeaderMapValue(
    proxy_wasm::WasmHeaderMapType type, std::string_view key,
    std::string_view value) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  result_.headers[std::string(key)] = std::string(value);
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestHttpContext::removeHeaderMapValue(
    proxy_wasm::WasmHeaderMapType type, std::string_view key) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  result_.headers.erase(std::string(key));
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestHttpContext::getHeaderMapPairs(
    proxy_wasm::WasmHeaderMapType type, proxy_wasm::Pairs* result) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  for (const auto& [key, val] : result_.headers) {
    result->push_back({key, val});
  }
  return proxy_wasm::WasmResult::Ok;
}
proxy_wasm::WasmResult TestHttpContext::setHeaderMapPairs(
    proxy_wasm::WasmHeaderMapType type, const proxy_wasm::Pairs& pairs) {
  if (type != phase_) return proxy_wasm::WasmResult::BadArgument;
  result_.headers.clear();
  for (const auto& [key, val] : pairs) {
    addHeaderMapValue(type, key, val);
  }
  return proxy_wasm::WasmResult::Ok;
}

proxy_wasm::WasmResult TestHttpContext::sendLocalResponse(
    uint32_t response_code, std::string_view body_text,
    proxy_wasm::Pairs additional_headers, uint32_t grpc_status,
    std::string_view details) {
  if (phase_ != proxy_wasm::WasmHeaderMapType::RequestHeaders &&
      phase_ != proxy_wasm::WasmHeaderMapType::ResponseHeaders) {
    return proxy_wasm::WasmResult::BadArgument;
  }
  result_.immediate_response = ImmediateResponse{};
  result_.immediate_response->body = body_text;
  result_.immediate_response->http_code = response_code;
  result_.immediate_response->grpc_code = grpc_status;
  result_.immediate_response->details = details;
  for (const auto& [key, val] : additional_headers) {
    result_.immediate_response->headers[std::string(key)] = std::string(val);
  }
  immediate_response_ = true;
  return proxy_wasm::WasmResult::Ok;
}

TestHttpContext::Result TestHttpContext::SendRequestHeaders(
    TestHttpContext::Headers headers) {
  phase_logs_.clear();
  result_ = Result{.headers = std::move(headers)};
  phase_ = proxy_wasm::WasmHeaderMapType::RequestHeaders;
  current_callback_ = TestHttpContext::CallbackType::RequestHeaders;
  result_.header_status =
      onRequestHeaders(result_.headers.size(), /*end_of_stream=*/false);
  phase_ = proxy_wasm::WasmHeaderMapType(-1);  // ideally 0 would mean unset
  return std::move(result_);
}

TestHttpContext::Result TestHttpContext::SendRequestBody(std::string body) {
  phase_logs_.clear();
  result_ = Result{};
  current_callback_ = TestHttpContext::CallbackType::RequestBody;
  if (immediate_response_) return Result{};
  body_buffer_.setOwned(std::move(body));
  result_.body_status =
      onRequestBody(body_buffer_.size(), /*end_of_stream=*/false);
  result_.body = body_buffer_.release();
  return std::move(result_);
}

TestHttpContext::Result TestHttpContext::SendResponseHeaders(
    TestHttpContext::Headers headers) {
  phase_logs_.clear();
  result_ = Result{};
  phase_ = proxy_wasm::WasmHeaderMapType::ResponseHeaders;
  current_callback_ = TestHttpContext::CallbackType::ResponseHeaders;
  if (immediate_response_) return Result{};
  result_.headers = std::move(headers);
  result_.header_status =
      onResponseHeaders(result_.headers.size(), /*end_of_stream=*/false);
  phase_ = proxy_wasm::WasmHeaderMapType(-1);  // ideally 0 would mean unset
  return std::move(result_);
}

TestHttpContext::Result TestHttpContext::SendResponseBody(std::string body) {
  phase_logs_.clear();
  result_ = Result{};
  current_callback_ = TestHttpContext::CallbackType::ResponseBody;
  if (immediate_response_) return Result{};
  body_buffer_.setOwned(std::move(body));
  result_.body_status =
      onResponseBody(body_buffer_.size(), /*end_of_stream=*/false);
  result_.body = body_buffer_.release();
  return std::move(result_);
}

absl::StatusOr<std::string> ReadDataFile(const std::string& path) {
  std::ifstream file(path, std::ios::binary);
  if (file.fail()) {
    return absl::NotFoundError(
        absl::StrCat("failed to open: ", path, ", error: ", strerror(errno)));
  }
  std::stringstream file_string_stream;
  file_string_stream << file.rdbuf();
  return file_string_stream.str();
}

std::vector<std::string> FindPlugins() {
  std::vector<std::string> out;
  for (const auto& entry : boost::filesystem::directory_iterator(
           boost::dll::program_location().parent_path())) {
    if (entry.path().extension() == ".wasm") {
      out.push_back(entry.path().string());
    }
  }
  return out;
}

absl::StatusOr<std::shared_ptr<proxy_wasm::PluginHandleBase>> CreatePluginVm(
    const std::string& engine, const std::string& wasm_bytes,
    const std::string& plugin_config, proxy_wasm::LogLevel min_log_level,
    ContextOptions options) {
  // Create a VM.
  auto vm = proxy_wasm::TestVm::makeVm(engine);
  static_cast<proxy_wasm::TestIntegration*>(vm->integration().get())
      ->setLogLevel(min_log_level);

  // Load the plugin.
  auto wasm = std::make_shared<TestWasm>(std::move(vm), std::move(options));
  if (!wasm->load(wasm_bytes, /*allow_precompiled=*/false)) {
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

  // Return plugin handle.
  return std::make_shared<proxy_wasm::PluginHandleBase>(
      std::make_shared<proxy_wasm::WasmHandleBase>(wasm), plugin);
}

absl::Status InitializePlugin(
    const std::shared_ptr<proxy_wasm::PluginHandleBase>& handle) {
  // Create root context, call onStart().
  proxy_wasm::ContextBase* root_context =
      handle->wasm()->start(handle->plugin());
  if (root_context == nullptr) {
    return absl::FailedPreconditionError("Plugin.start failed");
  }

  // On the root context, call onConfigure().
  if (!handle->wasm()->configure(root_context, handle->plugin())) {
    return absl::FailedPreconditionError("Plugin.configure failed");
  }
  return absl::OkStatus();
}

absl::StatusOr<std::shared_ptr<proxy_wasm::PluginHandleBase>>
CreateProxyWasmPlugin(const std::string& engine, const std::string& wasm_path,
                      const std::string& plugin_config,
                      proxy_wasm::LogLevel min_log_level) {
  // Read the wasm source.
  auto wasm = ReadDataFile(wasm_path);
  if (!wasm.ok()) {
    return wasm.status();
  }
  // Create VM and load wasm.
  auto handle = CreatePluginVm(engine, *wasm, plugin_config, min_log_level,
                               /*options=*/{});
  if (!handle.ok()) {
    return handle.status();
  }
  // Initialize plugin.
  auto init = InitializePlugin(*handle);
  if (!init.ok()) {
    return init;
  }
  return handle;
}

absl::Status HttpTest::CreatePlugin(const std::string& plugin_config) {
  // Enable tracing for functional (unit) tests.
  auto handle_or = CreateProxyWasmPlugin(engine(), path(), plugin_config,
                                         proxy_wasm::LogLevel::trace);
  if (!handle_or.ok()) {
    return handle_or.status();
  }
  handle_ = *handle_or;
  return absl::OkStatus();
}

}  // namespace service_extensions_samples
