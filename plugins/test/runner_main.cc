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
// - Structured output (JSON), adding product guidance in output
// - YAML config input support (--yaml instead of --proto)
// - Support wasm profiling (https://v8.dev/docs/profile)
// - Tune v8 compiler (v8_flags.liftoff_only, precompile, etc)

#include <cstdint>

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
#include "test/yaml_proto_converter.h"

ABSL_FLAG(std::string, proto, "", "Path to test config. Required.");
ABSL_FLAG(std::string, yaml, "", "Path to test config (.yaml format).");
ABSL_FLAG(std::string, plugin, "", "Override path to plugin wasm.");
ABSL_FLAG(std::string, config, "", "Override path to plugin config.");
ABSL_FLAG(std::string, logfile, "", "Emit plugin logs to disk or stdio.");
ABSL_FLAG(service_extensions_samples::pb::Env::LogLevel, loglevel,
          service_extensions_samples::pb::Env::UNDEFINED,
          "Override log_level.");
ABSL_FLAG(bool, test, true, "Option to disable config-requested tests.");
ABSL_FLAG(bool, bench, true, "Option to disable config-requested benchmarks.");
ABSL_FLAG(uint64_t, num_additional_streams, 0,
          "Number of additional streams to run in benchmarks.");
ABSL_FLAG(uint64_t, additional_stream_advance_rate, 0,
          "Number of additional streams to advance per benchmark iteration.");


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

// Determines input format based on file extension
enum class InputFormat {
  TEXTPROTO,
  YAML,
  UNKNOWN
};

InputFormat DetectInputFormat(const std::string& file_path) {
  if (file_path.length() >= 10 &&
      file_path.substr(file_path.length() - 10) == ".textproto") {
    return InputFormat::TEXTPROTO;
  }
  if (file_path.length() >= 5 &&
      (file_path.substr(file_path.length() - 5) == ".yaml" ||
       file_path.substr(file_path.length() - 4) == ".yml")) {
    return InputFormat::YAML;
  }
  return InputFormat::UNKNOWN;
}

absl::StatusOr<pb::TestSuite> ParseInputs(int argc, char** argv) {
  auto params = absl::ParseCommandLine(argc, argv);

  // Determine input file and format
  std::string cfg_path;
  InputFormat format = InputFormat::UNKNOWN;

  std::string proto_path = absl::GetFlag(FLAGS_proto);
  std::string yaml_path = absl::GetFlag(FLAGS_yaml);

  // Validate input flags
  if (!proto_path.empty() && !yaml_path.empty()) {
    return absl::InvalidArgumentError(
        "Cannot specify both --proto and --yaml flags. Use only one.");
  }

  if (proto_path.empty() && yaml_path.empty()) {
    return absl::InvalidArgumentError(
        "Either --proto or --yaml flag is required.");
  }

  if (!proto_path.empty()) {
    cfg_path = proto_path;
    format = InputFormat::TEXTPROTO;
  } else {
    cfg_path = yaml_path;
    format = InputFormat::YAML;
  }

  // Double-check format based on file extension if auto-detection is needed
  if (format == InputFormat::UNKNOWN) {
    format = DetectInputFormat(cfg_path);
    if (format == InputFormat::UNKNOWN) {
      return absl::InvalidArgumentError(
          absl::StrCat("Cannot determine format for file: ", cfg_path,
                       ". Use .textproto, .yaml, or .yml extension."));
    }
  }

  // Read input file
  auto cfg_bytes = ReadDataFile(cfg_path);
  if (!cfg_bytes.ok()) {
    return cfg_bytes.status();
  }

  // Parse based on format
  pb::TestSuite tests;
  switch (format) {
    case InputFormat::TEXTPROTO: {
      if (!google::protobuf::TextFormat::ParseFromString(*cfg_bytes, &tests)) {
        return absl::InvalidArgumentError("Failed to parse input textproto");
      }
      break;
    }
    case InputFormat::YAML: {
      auto yaml_result = pb::YamlProtoConverter::ConvertYamlToTestSuite(*cfg_bytes);
      if (!yaml_result.ok()) {
        return absl::InvalidArgumentError(
            absl::StrCat("Failed to parse input YAML: ", yaml_result.status().message()));
      }
      tests = std::move(*yaml_result);
      break;
    }
    default:
      return absl::InvalidArgumentError("Unsupported input format");
  }

  tests.mutable_env()->set_test_path(cfg_path);

  // Apply flag overrides.
  std::string plugin_override = absl::GetFlag(FLAGS_plugin);
  std::string config_override = absl::GetFlag(FLAGS_config);
  pb::Env::LogLevel mll_override = absl::GetFlag(FLAGS_loglevel);
  std::string logfile = absl::GetFlag(FLAGS_logfile);
  uint64_t num_additional_streams = absl::GetFlag(FLAGS_num_additional_streams);
  uint64_t additional_stream_advance_rate =
      absl::GetFlag(FLAGS_additional_stream_advance_rate);
  if (!plugin_override.empty()) {
    tests.mutable_env()->set_wasm_path(plugin_override);
  }
  if (!config_override.empty()) {
    tests.mutable_env()->set_config_path(config_override);
  }
  if (mll_override != pb::Env::UNDEFINED) {
    tests.mutable_env()->set_log_level(mll_override);
  }
  if (!logfile.empty()) {
    tests.mutable_env()->set_log_path(logfile);
  }
  if (num_additional_streams > 0) {
    tests.mutable_env()->set_num_additional_streams(num_additional_streams);
  }
  if (additional_stream_advance_rate > 0) {
    tests.mutable_env()->set_additional_stream_advance_rate(
        additional_stream_advance_rate);
  }
  if (tests.env().log_level() == pb::Env::TRACE) {
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
  bool tests_ok = true;
  if (absl::GetFlag(FLAGS_test)) {
    tests_ok = RUN_ALL_TESTS() == 0;
  } else {
    std::cout << "Skipping tests due to --test=false" << std::endl;
  }

  // Run performance benchmarks.
  if (have_benchmarks) {
    if (absl::GetFlag(FLAGS_bench)) {
      benchmark::RunSpecifiedBenchmarks();
      benchmark::Shutdown();
    } else {
      std::cout << "Skipping benchmarks due to --bench=false" << std::endl;
    }
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
