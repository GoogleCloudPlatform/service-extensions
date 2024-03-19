/*
 * Copyright 2024 Google LLC
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

#include "test/dynamic_test.h"

#include "absl/strings/substitute.h"
#include "benchmark/benchmark.h"
#include "dynamic_test.h"
#include "google/protobuf/text_format.h"
#include "gtest/gtest.h"
#include "re2/re2.h"
#include "test/framework.h"
#include "test/runner.pb.h"

namespace service_extensions_samples {

// Helper class to support string/regex positive/negative matching.
class StringMatcher {
 public:
  // Factory method. Creates a matcher or returns invalid argument status.
  static absl::StatusOr<StringMatcher> Create(const pb::StringMatcher& expect) {
    StringMatcher sm;
    sm.invert_ = expect.invert();
    if (expect.has_exact()) {
      sm.exact_ = expect.exact();
    } else if (expect.has_regex()) {
      sm.re_ = std::make_unique<RE2>(expect.regex(), RE2::Quiet);
      if (!sm.re_->ok()) {
        return absl::InvalidArgumentError(
            absl::StrCat("Bad regex: ", sm.re_->error()));
      }
    } else {
      return absl::InvalidArgumentError(
          "StringMatcher must specify 'exact' or 'regex' field.");
    }
    return sm;
  }

  // Check expectations against a list of strings.
  bool Matches(const std::vector<std::string>& contents) {
    for (const auto& msg : contents) {
      bool match = re_ ? RE2::FullMatch(msg, *re_) : msg == exact_;
      if (match) return !invert_;
    }
    return invert_;
  };

 private:
  StringMatcher() = default;

  bool invert_;
  std::string exact_;
  std::unique_ptr<RE2> re_ = nullptr;
};

absl::StatusOr<std::shared_ptr<proxy_wasm::PluginHandleBase>>
DynamicTest::LoadWasm(bool benchmark) {
  // Set log level. Default to INFO. Disable in benchmarks.
  auto ll = env_.min_log_level();
  if (ll == pb::Env::UNDEFINED) {
    ll = pb::Env::INFO;
  }
  if (benchmark) {
    ll = pb::Env::CRITICAL;
  }
  auto min_log_level = proxy_wasm::LogLevel(ll - 1);  // enum conversion, yuck

  // Load wasm bytes.
  auto wasm = ReadDataFile(env_.wasm_path());
  if (!wasm.ok()) return wasm.status();

  // Load plugin config from disk, if configured.
  std::string plugin_config = "";
  if (!env_.config_path().empty()) {
    auto config = ReadDataFile(env_.config_path());
    if (!config.ok()) return config.status();
    plugin_config = *config;
  }

  // Create VM and load wasm.
  return CreatePluginVm(engine_, *wasm, plugin_config, min_log_level);
}

void DynamicTest::TestBody() {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/false);
  ASSERT_TRUE(load_wasm.ok()) << load_wasm.status();
  auto handle = *load_wasm;

  // Initialize plugin.
  auto plugin_init = InitializePlugin(handle);
  ASSERT_TRUE(plugin_init.ok()) << plugin_init;
  TestContext* root_context = static_cast<TestContext*>(
      handle->wasm()->getRootContext(handle->plugin(),
                                     /*allow_closed=*/false));
  ASSERT_NE(root_context, nullptr);
  CheckForFailures("plugin_init", handle);
  CheckSideEffects("plugin_init", cfg_.plugin_init(), *root_context);

  // Initialize stream.
  auto stream = TestHttpContext(handle);
  CheckForFailures("stream_init", handle);
  CheckSideEffects("stream_init", cfg_.stream_init(), stream);

  // Exercise phase tests in sequence.
  if (cfg_.has_request_headers()) {
    const auto& invoke = cfg_.request_headers();
    auto res = stream.SendRequestHeaders(GenHeaders(invoke.input()));
    CheckForFailures("request_headers", handle);
    CheckPhaseResults("request_headers", invoke.result(), stream, res);
  }
  if (cfg_.request_body_size() > 0) {
    ADD_FAILURE() << "BODY processing not implemented yet";
  }
  if (cfg_.has_response_headers()) {
    const auto& invoke = cfg_.response_headers();
    auto res = stream.SendResponseHeaders(GenHeaders(invoke.input()));
    CheckForFailures("response_headers", handle);
    CheckPhaseResults("response_headers", invoke.result(), stream, res);
  }
  if (cfg_.response_body_size() > 0) {
    ADD_FAILURE() << "BODY processing not implemented yet";
  }

  // Tear down HTTP context.
  stream.TearDown();
  CheckForFailures("stream_destroy", handle);
  CheckSideEffects("stream_destroy", cfg_.stream_destroy(), stream);
}

#define BM_RETURN_IF_ERROR(status)          \
  if (!status.ok()) {                       \
    state.SkipWithError(status.ToString()); \
    return;                                 \
  }
#define BM_RETURN_IF_FAILED(handle)           \
  if (handle && handle->wasm()->isFailed()) { \
    state.SkipWithError("VM failed!");        \
    return;                                   \
  }

void DynamicTest::BenchPluginLifecycle(benchmark::State& state) {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/true);
  BM_RETURN_IF_ERROR(load_wasm.status());
  auto handle = *load_wasm;

  // Benchmark plugin initialization and teardown.
  for (auto _ : state) {
    // Create root context (start) and call configure on it.
    auto plugin_init = InitializePlugin(handle);
    BM_RETURN_IF_ERROR(plugin_init);
    // Explicit shutdown; required to recreate root context in the next loop.
    handle->wasm()->startShutdown(handle->plugin()->key());
    BM_RETURN_IF_FAILED(handle);
  }
}

void DynamicTest::BenchStreamLifecycle(benchmark::State& state) {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/true);
  BM_RETURN_IF_ERROR(load_wasm.status());
  auto handle = *load_wasm;

  // Initialize plugin.
  auto plugin_init = InitializePlugin(handle);
  BM_RETURN_IF_ERROR(plugin_init);
  BM_RETURN_IF_FAILED(handle);

  // Benchmark stream initialization and teardown.
  for (auto _ : state) {
    auto stream = TestHttpContext(handle);
    benchmark::DoNotOptimize(stream);
    BM_RETURN_IF_FAILED(handle);
  }
}

void DynamicTest::BenchHttpHandlers(benchmark::State& state) {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/true);
  BM_RETURN_IF_ERROR(load_wasm.status());
  auto handle = *load_wasm;

  // Initialize plugin.
  auto plugin_init = InitializePlugin(handle);
  BM_RETURN_IF_ERROR(plugin_init);
  BM_RETURN_IF_FAILED(handle);

  // Initialize stream.
  auto stream = TestHttpContext(handle);
  BM_RETURN_IF_FAILED(handle);

  // Benchmark all configured HTTP handlers.
  std::optional<TestHttpContext::Headers> request_headers;
  if (cfg_.has_request_headers()) {
    request_headers = GenHeaders(cfg_.request_headers().input());
  }
  std::optional<TestHttpContext::Headers> response_headers;
  if (cfg_.has_response_headers()) {
    response_headers = GenHeaders(cfg_.response_headers().input());
  }
  for (auto _ : state) {
    if (request_headers) {
      auto res = stream.SendRequestHeaders(*request_headers);
      benchmark::DoNotOptimize(res);
      BM_RETURN_IF_FAILED(handle);
    }
    // Future: send request BODY here.
    if (response_headers) {
      auto res = stream.SendResponseHeaders(*response_headers);
      benchmark::DoNotOptimize(res);
      BM_RETURN_IF_FAILED(handle);
    }
    // Future: send response BODY here.
  }
}

void DynamicTest::CheckForFailures(
    const std::string& phase,
    const std::shared_ptr<proxy_wasm::PluginHandleBase>& handle) {
  if (handle->wasm()->isFailed()) {
    ADD_FAILURE() << absl::Substitute("[$0] Wasm VM failed!", phase);
  }
}

void DynamicTest::CheckSideEffects(const std::string& phase,
                                   const pb::Expectation& expect,
                                   const TestContext& context) {
  // Check logging.
  for (const auto& match : expect.log()) {
    FindString(phase, "log", match, context.phase_logs());
  }
}

void DynamicTest::CheckPhaseResults(const std::string& phase,
                                    const pb::Expectation& expect,
                                    const TestContext& context,
                                    const TestHttpContext::Result& result) {
  // Check header values.
  for (const auto& header : expect.has_header()) {
    auto it = result.headers.find(header.key());
    if (it == result.headers.end()) {
      ADD_FAILURE() << absl::Substitute("[$0] Missing header '$1'", phase,
                                        header.key());
    } else if (it->second != header.value()) {
      ADD_FAILURE() << absl::Substitute(
          "[$0] Header '$1' value is '$2', expected '$3'", phase, header.key(),
          it->second, header.value());
    }
  }
  // Check header removals.
  for (const auto& header : expect.no_header()) {
    auto it = result.headers.find(header.key());
    if (it != result.headers.end()) {
      ADD_FAILURE() << absl::Substitute(
          "[$0] Header '$1' value is '$2', expected removed", phase,
          header.key(), it->second);
    }
  }
  // Check body content.
  for (const auto& match : expect.body()) {
    FindString(phase, "body", match, {result.body});
  }
  // Check immediate response.
  bool is_continue =
      result.status == proxy_wasm::FilterHeadersStatus::Continue ||
      result.status == proxy_wasm::FilterHeadersStatus::ContinueAndEndStream;
  if (expect.has_immediate() == is_continue) {
    ADD_FAILURE() << absl::Substitute(
        "[$0] Expected $1, status is $2", phase,
        expect.has_immediate() ? "immediate reply (stop filters status)"
                               : "no immediate reply (continue status)",
        result.status);
  }
  if (expect.has_immediate() == (result.http_code == 0)) {
    ADD_FAILURE() << absl::Substitute(
        "[$0] Expected $1, HTTP code is $2", phase,
        expect.has_immediate() ? "immediate reply (HTTP code > 0)"
                               : "no immediate reply (HTTP code == 0)",
        result.http_code);
  }
  const auto& imm = expect.immediate();
  if (imm.has_http_status() && imm.http_status() != result.http_code) {
    ADD_FAILURE() << absl::Substitute("[$0] HTTP status is $1, expected $2",
                                      phase, result.http_code,
                                      imm.http_status());
  }
  if (imm.has_grpc_status() && imm.grpc_status() != result.grpc_code) {
    ADD_FAILURE() << absl::Substitute("[$0] gRPC status is $1, expected $2",
                                      phase, result.grpc_code,
                                      imm.grpc_status());
  }
  if (imm.has_details() && imm.details() != result.details) {
    ADD_FAILURE() << absl::Substitute("[$0] gRPC detail is $1, expected $2",
                                      phase, result.details, imm.details());
  }
  // Check logging.
  for (const auto& match : expect.log()) {
    FindString(phase, "log", match, context.phase_logs());
  }
}

void DynamicTest::FindString(const std::string& phase, const std::string& type,
                             const pb::StringMatcher& expect,
                             const std::vector<std::string>& contents) {
  auto matcher = StringMatcher::Create(expect);
  if (!matcher.ok()) {
    ADD_FAILURE() << absl::Substitute("[$0] $1", phase,
                                      matcher.status().ToString());
    return;
  }
  if (!matcher->Matches(contents)) {
    ADD_FAILURE() << absl::Substitute(
        "[$0] expected $1 of $2 $3: '$4', actual: '$5'", phase,
        expect.invert() ? "absence" : "presence",
        expect.has_regex() ? "regex" : "exact", type,
        expect.has_regex() ? expect.regex() : expect.exact(),
        absl::StrJoin(contents, ","));
  }
}

TestHttpContext::Headers DynamicTest::GenHeaders(const pb::Input& input) {
  TestHttpContext::Headers hdrs;
  for (const auto& header : input.header()) {
    hdrs.emplace(header.key(), header.value());
  }
  return hdrs;
}

}  // namespace service_extensions_samples
