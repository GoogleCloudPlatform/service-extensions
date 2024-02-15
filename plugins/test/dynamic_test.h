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

#include "gtest/gtest.h"
#include "test/framework.h"
#include "test/runner.pb.h"

namespace service_extensions_samples {

// Fixture for DynamicTest. Currently does nothing, but kept separate because
// this could share plugin lifecycle across individual tests.
//
// TODO consider an engine-parameterized fixture that owns plugin lifecycle
// (see INSTANTIATE_TEST_SUITE_P). It's tricky because each fixture (engine)
// needs its own class type.
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
  explicit DynamicTest(const std::string& engine, const pb::Runtime& env,
                       const pb::Test& cfg)
      : engine_(engine), env_(env), cfg_(cfg) {}

  // Core test logic, driven by the proto test config.
  void TestBody() override;

 private:
  // Helper to check for wasm engine failures.
  void CheckForFailures(
      const std::string& phase,
      const std::shared_ptr<proxy_wasm::PluginHandleBase>& handle);

  // Helper to check lifecycle phase side effects (e.g. logging).
  void CheckSideEffects(const std::string& phase, const pb::Expectation& expect,
                        const TestContext& context);

  // Helper to check phase expectations against outputs.
  void CheckPhaseResults(const std::string& phase,
                         const pb::Expectation& expect,
                         const TestContext& context,
                         const TestHttpContext::Result& result);

  // Helper to match string expectations.
  void FindString(const std::string& phase, const std::string& type,
                  const pb::StringMatcher& expect,
                  const std::vector<std::string>& contents);

  // Helper to generate Headers struct from proto.
  TestHttpContext::Headers GenHeaders(const pb::Input& input);

  std::string engine_;
  pb::Runtime env_;
  pb::Test cfg_;
};

}  // namespace service_extensions_samples
