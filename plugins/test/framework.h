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

#pragma once

#include <boost/algorithm/string.hpp>
#include <boost/filesystem/path.hpp>
#include <string>

#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "absl/strings/str_cat.h"
#include "gtest/gtest.h"
#include "include/proxy-wasm/exports.h"
#include "include/proxy-wasm/wasm.h"
#include "test/utility.h"

namespace service_extensions_samples {

// Parameters to customize Context behaviors.
struct ContextOptions {
  // Wasm logging output file.
  std::ofstream log_file;
  // Static time returned to wasm. Must be non-zero for Go plugin
  // initialization.
  absl::Time clock_time = absl::UnixEpoch() + absl::Milliseconds(1);
};

// Buffer class to handle copying to and from an individual BODY chunk.
class Buffer : public proxy_wasm::BufferBase {
 public:
  Buffer() = default;

  // proxy_wasm::BufferInterface
  size_t size() const override;
  proxy_wasm::WasmResult copyTo(proxy_wasm::WasmBase* wasm, size_t start,
                                size_t length, uint64_t ptr_ptr,
                                uint64_t size_ptr) const override;
  proxy_wasm::WasmResult copyFrom(size_t start, size_t length,
                                  std::string_view data) override;

  // proxy_wasm::BufferBase
  void clear() override {
    proxy_wasm::BufferBase::clear();
    owned_string_buffer_ = "";
  }

  void setOwned(std::string data) {
    clear();
    owned_string_buffer_ = std::move(data);
  }
  std::string release() { return std::move(owned_string_buffer_); }

 private:
  // Buffer for a body chunk.
  std::string owned_string_buffer_;
};

// TestContext is GCP-like ProxyWasm context (shared for VM + Root + Stream).
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
  // --- END   Wasm facing API ---

  // --- BEGIN Testing facilities ---
  // Unsafe access to logs. Not thread safe w.r.t. plugin execution.
  const std::vector<std::string>& phase_logs() const { return phase_logs_; }
  // Options to customize context behavior.
  ContextOptions& options() const;
  // --- END   Testing facilities ---

 protected:
  std::vector<std::string> phase_logs_;

 private:
  proxy_wasm::BufferBase plugin_config_;
};

// TestHttpContext is a GCP-like ProxyWasm Stream context. It primarily
// implements HTTP methods usable by Wasm.
//
// The implementation is an incomplete test-only approximation of HTTP-compliant
// header handling. It's missing at least the following:
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
  ~TestHttpContext() override { TearDown(); }

  // Exposed so that tests can invoke handlers and verify side effects.
  void TearDown() {
    if (!torn_down_) {
      phase_logs_.clear();
      // For Golang Stream Contexts are only called on on_log, not on on_done. See:
      // https://github.com/tetratelabs/proxy-wasm-go-sdk/blob/main/proxywasm/internal/abi_callback_lifecycle.go#L40
      this->onLog();     // calls wasm if VM not failed
      this->onDone();    // calls wasm if VM not failed
      this->onDelete();  // calls wasm if VM not failed and create succeeded
      torn_down_ = true;
    }
  }

  // --- BEGIN Wasm facing API ---
  proxy_wasm::BufferInterface* getBuffer(
      proxy_wasm::WasmBufferType type) override;
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

  // Ignore failStream, avoid calling unimplemented closeStream.
  void failStream(proxy_wasm::WasmStreamType) override {}
  proxy_wasm::WasmResult sendLocalResponse(uint32_t response_code,
                                           std::string_view body_text,
                                           proxy_wasm::Pairs additional_headers,
                                           uint32_t grpc_status,
                                           std::string_view details) override;
  // --- END Wasm facing API ---

  // Testing types. Optimized for ease of use, not performance.

  // Case insensitive string comparator.
  struct caseless_compare {
    bool operator()(absl::string_view a, absl::string_view b) const {
      return boost::ilexicographical_compare(a, b);
    }
  };

  // Key-sorted header map with case-insensitive key comparison.
  class Headers : public std::map<std::string, std::string, caseless_compare> {
   public:
    void InsertOrAppend(absl::string_view key, absl::string_view value) {
      auto& val = operator[](std::string(key));
      if (val.empty()) {
        val = std::string(value);
      } else {
        val = absl::StrCat(val, ", ", value);  // RFC 9110 Field Order
      }
    }
  };

  struct Result {
    // Filter status for headers returned by handler.
    proxy_wasm::FilterHeadersStatus header_status;
    // Mutated headers, also used for immediate response.
    Headers headers = {};
    // Filter status for body returned by handler.
    proxy_wasm::FilterDataStatus body_status;
    // Mutated body, also used for immediate response.
    std::string body = "";
    // Immediate response parameters.
    uint32_t http_code = 0;    // sent to user via proxy
    uint32_t grpc_code = 0;    // sent to proxy
    std::string details = "";  // sent to proxy
  };

  // Testing helpers. Use these instead of direct on*Headers methods.
  Result SendRequestHeaders(Headers headers);
  Result SendRequestBody(std::string body);
  Result SendResponseHeaders(Headers headers);
  Result SendResponseBody(std::string body);

  enum CallbackType {
    None,
    RequestHeaders,
    RequestBody,
    ResponseHeaders,
    ResponseBody,
  };

 private:
  // Ensure that we invoke teardown handlers just once.
  bool torn_down_ = false;
  // State tracked during a headers call. Invalid otherwise.
  proxy_wasm::WasmHeaderMapType phase_;
  Result result_;

  Buffer body_buffer_;
  CallbackType current_callback_;
};

// TestWasm is a light wrapper enabling custom TestContext.
class TestWasm : public proxy_wasm::WasmBase {
 public:
  TestWasm(std::unique_ptr<proxy_wasm::WasmVm> vm, ContextOptions options)
      : proxy_wasm::WasmBase(std::move(vm), /*vm_id=*/"",
                             /*vm_configuration=*/"",
                             /*vm_key=*/"", /*envs=*/{},
                             /*allowed_capabilities=*/{}),
        options_(std::move(options)) {}

  proxy_wasm::ContextBase* createVmContext() override {
    return new TestContext(this);
  };

  proxy_wasm::ContextBase* createRootContext(
      const std::shared_ptr<proxy_wasm::PluginBase>& plugin) override {
    return new TestContext(this, plugin);
  }

  ContextOptions& options() { return options_; }

 private:
  ContextOptions options_;
};

// Helper to read a file from disk.
absl::StatusOr<std::string> ReadDataFile(const std::string& path);

// Helper to scan for .wasm files next to the executing binary.
std::vector<std::string> FindPlugins();

// Helper to create a VM and load wasm.
absl::StatusOr<std::shared_ptr<proxy_wasm::PluginHandleBase>> CreatePluginVm(
    const std::string& engine, const std::string& wasm_bytes,
    const std::string& plugin_config, proxy_wasm::LogLevel min_log_level,
    ContextOptions options);

// Helper to initialize a plugin.
absl::Status InitializePlugin(
    const std::shared_ptr<proxy_wasm::PluginHandleBase>& handle);

// Helper to create and initialize a plugin. Logging defaults to off.
absl::StatusOr<std::shared_ptr<proxy_wasm::PluginHandleBase>>
CreateProxyWasmPlugin(
    const std::string& engine, const std::string& wasm_path,
    const std::string& plugin_config = "",
    proxy_wasm::LogLevel min_log_level = proxy_wasm::LogLevel::critical);

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
  absl::Status CreatePlugin(const std::string& plugin_config = "");

  TestContext* root() {
    if (!handle_) return nullptr;
    return static_cast<TestContext*>(
        handle_->wasm()->getRootContext(handle_->plugin(),
                                        /*allow_closed=*/false));
  }

  std::shared_ptr<proxy_wasm::PluginHandleBase> handle_;
};

// Helper to register a test fixture to run for all engines and plugins.
// Consider adding a param printer function.
#define REGISTER_TESTS(fixture)                                             \
  INSTANTIATE_TEST_SUITE_P(                                                 \
      Tests, fixture,                                                       \
      ::testing::Combine(::testing::ValuesIn(proxy_wasm::getWasmEngines()), \
                         ::testing::ValuesIn(FindPlugins())));

// Helper to register a benchmark to run for all engines and plugins.
// Consider adding Apply(cb) to allow callers to configure benchmarks.
#define REGISTER_BENCH(fn)                                                    \
  struct Register_##fn {                                                      \
    Register_##fn() {                                                         \
      for (auto& engine : proxy_wasm::getWasmEngines()) {                     \
        for (auto& plugin : FindPlugins()) {                                  \
          auto file = boost::filesystem::path(plugin).filename().string();    \
          benchmark::RegisterBenchmark(                                       \
              absl::StrCat(#fn, "_", engine, "_", file), fn, engine, plugin); \
        }                                                                     \
      }                                                                       \
    }                                                                         \
  } register_##fn;

}  // namespace service_extensions_samples
