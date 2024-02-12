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
#include "dynamic_test.h"
#include "google/protobuf/text_format.h"
#include "gtest/gtest.h"
#include "re2/re2.h"
#include "test/framework.h"
#include "test/runner.pb.h"

namespace service_extensions_samples {

void DynamicTest::TestBody() {
  // Set log level. Default to INFO. Disable in benchmarks.
  auto ll = env_.min_log_level();
  if (ll == pb::Runtime::UNDEFINED) {
    ll = pb::Runtime::INFO;
  }
  if (false) {  // TODO disable logging in benchmark mode.
    ll = pb::Runtime::CRITICAL;
  }
  auto min_log_level = proxy_wasm::LogLevel(ll - 1);  // enum conversion, yuck

  // Load wasm bytes.
  auto wasm = ReadDataFile(env_.wasm_path());
  ASSERT_TRUE(wasm.ok()) << wasm.status();

  // Load plugin config from disk, if configured.
  std::string plugin_config = "";
  if (!env_.config_path().empty()) {
    // std::cout << "Loading config: " << env_.config_path() << std::endl;
    auto config = ReadDataFile(env_.config_path());
    ASSERT_TRUE(config.ok()) << config.status();
    plugin_config = *config;
  }

  // Create VM and load wasm.
  auto handle = CreatePluginVm(engine_, *wasm, plugin_config, min_log_level);
  ASSERT_TRUE(handle.ok()) << handle.status();

  // Initialize plugin.
  auto plugin_init = InitializePlugin(*handle);
  ASSERT_TRUE(plugin_init.ok()) << plugin_init;
  TestContext* root_context = static_cast<TestContext*>(
      (*handle)->wasm()->getRootContext((*handle)->plugin(),
                                        /*allow_closed=*/false));
  CheckForFailures("plugin_init", *handle);
  CheckSideEffects("plugin_init", cfg_.plugin_init(), *root_context);

  // Create HTTP context.
  auto stream = TestHttpContext(*handle);
  CheckForFailures("stream_init", *handle);
  CheckSideEffects("stream_init", cfg_.stream_init(), stream);

  // Exercise phase tests in sequence.
  if (cfg_.has_request_headers()) {
    const auto& invoke = cfg_.request_headers();
    auto res = stream.SendRequestHeaders(GenHeaders(invoke.input()));
    CheckForFailures("request_headers", *handle);
    CheckPhaseResults("request_headers", invoke.result(), stream, res);
  }
  if (cfg_.request_body_size() > 0) {
    ADD_FAILURE() << "BODY processing not implemented yet";
  }
  if (cfg_.has_response_headers()) {
    const auto& invoke = cfg_.response_headers();
    auto res = stream.SendResponseHeaders(GenHeaders(invoke.input()));
    CheckForFailures("response_headers", *handle);
    CheckPhaseResults("response_headers", invoke.result(), stream, res);
  }
  if (cfg_.response_body_size() > 0) {
    ADD_FAILURE() << "BODY processing not implemented yet";
  }

  // Tear down HTTP context.
  stream.TearDown();
  CheckForFailures("stream_destroy", *handle);
  CheckSideEffects("stream_destroy", cfg_.stream_destroy(), stream);
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
  for (const auto& log : expect.log()) {
    FindLog(phase, context, log);
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
  if (expect.has_set_body()) {
    if (result.body != expect.set_body()) {
      ADD_FAILURE() << absl::Substitute(
          "[$0]\nBody value is:\n$1\nExpected:\n$2", phase, result.body,
          expect.set_body());
    }
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
  for (const auto& log : expect.log()) {
    FindLog(phase, context, log);
  }
}

void DynamicTest::FindLog(const std::string& phase, const TestContext& context,
                          const pb::Expectation::Log& expect) {
  // Define a matcher.
  std::optional<RE2> re;
  std::function<bool(const std::string&)> match;
  if (expect.has_message()) {
    match = [&](const std::string& log) { return log == expect.message(); };
  } else if (expect.has_regex()) {
    re.emplace(expect.regex(), RE2::Quiet);
    if (!re->ok()) {
      ADD_FAILURE() << absl::Substitute("[$0] Regex '$1' failed to compile: $2",
                                        phase, expect.regex(), re->error());
      return;
    }
    match = [&](const std::string& log) { return RE2::FullMatch(log, *re); };
  }

  // Define a helper to iterate and match emitted logs.
  auto find = [&]() {
    for (const auto& msg : context.phase_logs()) {
      if (match(msg) && !expect.invert()) return true;
    }
    return expect.invert();
  };

  // Run test.
  if (!find()) {
    ADD_FAILURE() << absl::Substitute(
        "[$0] Log $1: $2 '$3'", phase,
        expect.invert() ? "found but not expected" : "expected but not found",
        expect.has_regex() ? "regex match" : "exact text",
        expect.has_regex() ? expect.regex() : expect.message());
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
