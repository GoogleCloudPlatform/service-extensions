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

#pragma once

#include "benchmark/benchmark.h"
#include "gtest/gtest.h"
#include "test/framework.h"
#include "test/runner.pb.h"

namespace service_extensions_samples {

// Fixture for DynamicTest. Currently does nothing, but kept separate because
// this could share plugin lifecycle across individual tests.
//
// TODO consider a fixture parameterized on engine + env that owns a VM. It
// could load files from disk and call CreatePluginVm (once). It's tricky
// because each fixture needs its own class type (see INSTANTIATE_TEST_SUITE_P).
class DynamicFixture : public testing::Test {
 public:
  // static void SetUpTestSuite() { std::cout << "FIXTURE\n"; }
  // static void TearDownTestSuite() { ... }
  // void SetUp() override { std::cout << "TEST\n"; }
  // void TearDown() override { ... }
};

// A class that owns running a configurable unit test and/or benchmark. The
// phases to execute and expectations to validate are in pb::Test. The engine
// and runtime may later be extracted into the fixture.
class DynamicTest : public DynamicFixture {
 public:
  explicit DynamicTest(const std::string& engine, const pb::Env& env,
                       const pb::Test& cfg)
      : engine_(engine), env_(env), cfg_(cfg) {}

  // Unit test logic, driven by the proto test config.
  void TestBody() override;

  // Benchmark functions.
  // Plugin lifecycle: onStart, onConfigure, onDone.
  void BenchPluginLifecycle(benchmark::State& state);
  // Stream lifecycle: onCreate, onDone.
  void BenchStreamLifecycle(benchmark::State& state);
  // HTTP handlers: onRequest*, onResponse*
  void BenchHttpHandlers(benchmark::State& state);

 private:
  // Initialize VM + load wasm.
  absl::StatusOr<std::shared_ptr<proxy_wasm::PluginHandleBase>> LoadWasm(
      bool benchmark);

  // Test helper to check lifecycle phase side effects (e.g. logging).
  void CheckSideEffects(const std::string& phase, const pb::Expectation& expect,
                        const TestContext& context);

  // Test helper to check phase expectations against outputs.
  void CheckPhaseResults(const std::string& phase,
                         const pb::Expectation& expect,
                         const TestContext& context,
                         const TestHttpContext::Result& result);

  // Test helper to match string expectations.
  void FindString(const std::string& phase, const std::string& type,
                  const pb::StringMatcher& expect,
                  const std::vector<std::string>& contents);

  // Helper to generate Headers struct from proto, string, or file.
  absl::StatusOr<TestHttpContext::Headers> ParseHeaders(const pb::Input& input,
                                                        bool is_request);

  // Helper to generate body string from test config.
  absl::StatusOr<std::string> ParseBodyInput(const pb::Input& input);

  // Helper to break body down into chunks.
  std::vector<std::string> ChunkBody(const std::string& complete_body,
                                     const pb::Test& test);

  // Helper to prep body callbacks for benchmarking.
  absl::StatusOr<std::vector<std::string>> PrepBodyCallbackBenchmark(
      const pb::Test& test,
      google::protobuf::RepeatedPtrField<pb::Invocation> invocations);

  // Bench helper to emit custom stats.
  void EmitStats(benchmark::State& state, proxy_wasm::PluginHandleBase& handle,
                 const TestContext& context);

  std::string engine_;
  pb::Env env_;
  pb::Test cfg_;
};

}  // namespace service_extensions_samples
