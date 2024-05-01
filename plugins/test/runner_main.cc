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

// A dynamic test runner for Wasm plugins. Given a proto specification, this
// binary provides various inputs to a ProxyWasm plugin for each test, and
// validates a configured set of expectations about output and side effects.
//
// TODO Future features
// - Publish test runner as Docker image
// - Option to print all logs to file/stdout
// - Option to set the clock time via config
// - Support wasm profiling (https://v8.dev/docs/profile)
// - Tune v8 compiler (v8_flags.liftoff_only, precompile, etc)
// - YAML config input support (--yaml instead of --proto)
// - Structured output (JSON) rather than stdout/stderr
// - Crash / death tests?

#include "absl/flags/flag.h"
#include "absl/flags/parse.h"
#include "absl/strings/substitute.h"
#include "benchmark/benchmark.h"
#include "google/protobuf/text_format.h"
#include "gtest/gtest.h"
#include "re2/re2.h"
#include "test/dynamic_test.h"
#include "test/framework.h"
#include "test/runner.pb.h"

ABSL_FLAG(std::string, proto, "", "Path to test config. Required.");
ABSL_FLAG(std::string, plugin, "", "Override path to plugin wasm.");
ABSL_FLAG(std::string, config, "", "Override path to plugin config.");
ABSL_FLAG(service_extensions_samples::pb::Env::LogLevel, min_log_level,
          service_extensions_samples::pb::Env::UNDEFINED,
          "Override min_log_level.");

namespace service_extensions_samples {

// Proto enum flag (de)serialization.
namespace pb {
bool AbslParseFlag(absl::string_view text, pb::Env::LogLevel* ll,
                   std::string* error) {
  return Env::LogLevel_Parse(std::string(text), ll);
}
std::string AbslUnparseFlag(pb::Env::LogLevel ll) {
  return Env_LogLevel_Name(ll);
}
}  // namespace pb

absl::StatusOr<pb::TestSuite> ParseInputs(int argc, char** argv) {
  auto params = absl::ParseCommandLine(argc, argv);

  // Parse test config.
  std::string cfg_path = absl::GetFlag(FLAGS_proto);
  if (cfg_path.empty()) {
    return absl::InvalidArgumentError("Flag --proto is required.");
  }
  auto cfg_bytes = ReadDataFile(cfg_path);
  if (!cfg_bytes.ok()) {
    return cfg_bytes.status();
  }
  pb::TestSuite tests;
  if (!google::protobuf::TextFormat::ParseFromString(*cfg_bytes, &tests)) {
    return absl::InvalidArgumentError("Failed to parse input proto");
  }
  // Apply flag overrides.
  std::string plugin_override = absl::GetFlag(FLAGS_plugin);
  std::string config_override = absl::GetFlag(FLAGS_config);
  pb::Env::LogLevel mll_override = absl::GetFlag(FLAGS_min_log_level);
  if (!plugin_override.empty()) {
    tests.mutable_env()->set_wasm_path(plugin_override);
  }
  if (!config_override.empty()) {
    tests.mutable_env()->set_config_path(config_override);
  }
  if (pb::Env::LogLevel_IsValid(mll_override)) {
    tests.mutable_env()->set_min_log_level(mll_override);
  }
  if (tests.env().min_log_level() == pb::Env::TRACE) {
    std::cout << "TRACE from runner: final config:\n" << tests.DebugString();
  }
  return tests;
}

absl::Status RunTests(const pb::TestSuite& cfg) {
  // Register tests and benchmarks.
  bool have_benchmarks = false;
  for (const auto& engine : proxy_wasm::getWasmEngines()) {
    for (const auto& test : cfg.test()) {
      // Register functional tests.
      testing::RegisterTest(
          absl::StrCat("Test_", engine).c_str(), test.name().c_str(), nullptr,
          nullptr, __FILE__, __LINE__,
          // Important to use the fixture type as the return type here.
          [=]() -> DynamicFixture* {
            return new DynamicTest(engine, cfg.env(), test);
          });

      // Register benchmarks.
      if (test.benchmark()) {
        // Benchmark lifecycle costs just once.
        if (!have_benchmarks) {
          have_benchmarks = true;
          benchmark::RegisterBenchmark(
              absl::Substitute("Bench_$0.PluginLifecycle", engine),
              [=](benchmark::State& state) {
                DynamicTest dt(engine, cfg.env(), test);
                dt.BenchPluginLifecycle(state);
              });
          benchmark::RegisterBenchmark(
              absl::Substitute("Bench_$0.StreamLifecycle", engine),
              [=](benchmark::State& state) {
                DynamicTest dt(engine, cfg.env(), test);
                dt.BenchStreamLifecycle(state);
              });
        }
        // Benchmark HTTP handlers for each opted-in test.
        benchmark::RegisterBenchmark(
            absl::Substitute("Bench_$0.$1", engine, test.name()),
            [=](benchmark::State& state) {
              DynamicTest dt(engine, cfg.env(), test);
              dt.BenchHttpHandlers(state);
            });
      }
    }
  }

  // Run functional tests.
  bool tests_ok = RUN_ALL_TESTS() == 0;

  // Run performance benchmarks.
  if (have_benchmarks) {
    benchmark::RunSpecifiedBenchmarks();
    benchmark::Shutdown();
  }

  return tests_ok ? absl::OkStatus() : absl::AbortedError("tests failed");
}

absl::Status main(int argc, char** argv) {
  // Initialize testing args.
  testing::InitGoogleTest(&argc, argv);
  benchmark::Initialize(&argc, argv);

  // Parse runner args.
  auto cfg = ParseInputs(argc, argv);
  if (!cfg.ok()) {
    return cfg.status();
  }

  return RunTests(*cfg);
}

}  // namespace service_extensions_samples

int main(int argc, char** argv) {
  absl::Status res = service_extensions_samples::main(argc, argv);
  if (!res.ok()) {
    std::cerr << res << std::endl;
    return 1;
  }
  return 0;
}
