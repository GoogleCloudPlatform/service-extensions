/*
 * Copyright 2025 Google LLC
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

#include "yaml_proto_converter.h"

#include <algorithm>
#include <optional>
#include <string>
#include <vector>
#include <yaml-cpp/yaml.h>

#include "absl/status/status.h"
#include "absl/strings/ascii.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_split.h"
#include "absl/strings/strip.h"
#include "google/protobuf/repeated_field.h"

namespace service_extensions_samples::pb {
namespace {

// Forward declarations for helper functions.
absl::Status ConvertTest(const YAML::Node& yaml_test, Test* proto_test);
absl::Status ConvertInvocation(const YAML::Node& yaml_invocation, Invocation* proto_invocation);
absl::Status ConvertInput(const YAML::Node& yaml_input, Input* proto_input);
absl::Status ConvertExpectation(const YAML::Node& yaml_expectation, Expectation* proto_expectation);
absl::Status ConvertHeader(const YAML::Node& yaml_header, Header* proto_header);
absl::Status ConvertStringMatcher(const YAML::Node& yaml_matcher, StringMatcher* proto_matcher);
absl::Status ConvertEnv(const YAML::Node& yaml_env, Env* proto_env);
absl::Status ConvertImmediate(const YAML::Node& yaml_immediate, Expectation::Immediate* proto_immediate);
absl::Status ConvertHeaders(const YAML::Node& yaml_headers, google::protobuf::RepeatedPtrField<Header>* proto_headers);
absl::Status ConvertStringMatchers(const YAML::Node& yaml_matchers, google::protobuf::RepeatedPtrField<StringMatcher>* proto_matchers);
absl::Status ConvertInvocations(const YAML::Node& yaml_invocations, google::protobuf::RepeatedPtrField<Invocation>* proto_invocations);

std::optional<std::string> GetStringValue(const YAML::Node& node) {
  if (!node.IsDefined() || node.IsNull()) {
    return std::nullopt;
  }
  return node.as<std::string>();
}

std::optional<int32_t> GetIntValue(const YAML::Node& node) {
  if (!node.IsDefined() || node.IsNull()) {
    return std::nullopt;
  }
  return node.as<int32_t>();
}

std::optional<int64_t> GetInt64Value(const YAML::Node& node) {
  if (!node.IsDefined() || node.IsNull()) {
    return std::nullopt;
  }
  return node.as<int64_t>();
}

std::optional<uint32_t> GetUInt32Value(const YAML::Node& node) {
  if (!node.IsDefined() || node.IsNull()) {
    return std::nullopt;
  }
  return node.as<uint32_t>();
}

std::optional<uint64_t> GetUInt64Value(const YAML::Node& node) {
  if (!node.IsDefined() || node.IsNull()) {
    return std::nullopt;
  }
  return node.as<uint64_t>();
}

std::optional<bool> GetBoolValue(const YAML::Node& node) {
  if (!node.IsDefined() || node.IsNull()) {
    return std::nullopt;
  }
  return node.as<bool>();
}

std::optional<std::string> GetBytesValue(const YAML::Node& node) {
  if (!node.IsDefined() || node.IsNull()) {
    return std::nullopt;
  }
  return node.as<std::string>();
}

Env::LogLevel ConvertLogLevel(const std::string& level_str) {
  std::string upper_level = absl::AsciiStrToUpper(level_str);
  if (upper_level == "TRACE") return Env::TRACE;
  if (upper_level == "DEBUG") return Env::DEBUG;
  if (upper_level == "INFO") return Env::INFO;
  if (upper_level == "WARN") return Env::WARN;
  if (upper_level == "ERROR") return Env::ERROR;
  if (upper_level == "CRITICAL") return Env::CRITICAL;
  return Env::UNDEFINED;
}

absl::Status ConvertTest(const YAML::Node& yaml_test, Test* proto_test) {
  if (!yaml_test.IsMap()) {
    return absl::InvalidArgumentError("Test must be a YAML map");
  }
  proto_test->set_name(GetStringValue(yaml_test["name"]).value_or(""));
  proto_test->set_benchmark(GetBoolValue(yaml_test["benchmark"]).value_or(false));
  if (yaml_test["body_chunking_plan"]) {
    const auto& chunking_plan = yaml_test["body_chunking_plan"];
    if (chunking_plan["num_chunks"]) {
      proto_test->set_num_chunks(GetIntValue(chunking_plan["num_chunks"]).value_or(0));
    } else if (chunking_plan["chunk_size"]) {
      proto_test->set_chunk_size(GetInt64Value(chunking_plan["chunk_size"]).value_or(0));
    }
  }
  if (yaml_test["request_headers"]) {
    if (absl::Status status = ConvertInvocation(yaml_test["request_headers"], proto_test->mutable_request_headers()); !status.ok()) return status;
  }
  if (yaml_test["request_body"] && yaml_test["request_body"].IsSequence()) {
    if (absl::Status status = ConvertInvocations(yaml_test["request_body"], proto_test->mutable_request_body()); !status.ok()) return status;
  }
  if (yaml_test["response_headers"]) {
    if (absl::Status status = ConvertInvocation(yaml_test["response_headers"], proto_test->mutable_response_headers()); !status.ok()) return status;
  }
  if (yaml_test["response_body"] && yaml_test["response_body"].IsSequence()) {
    if (absl::Status status = ConvertInvocations(yaml_test["response_body"], proto_test->mutable_response_body()); !status.ok()) return status;
  }
  if (yaml_test["plugin_init"]) {
    if (absl::Status status = ConvertExpectation(yaml_test["plugin_init"], proto_test->mutable_plugin_init()); !status.ok()) return status;
  }
  if (yaml_test["stream_init"]) {
    if (absl::Status status = ConvertExpectation(yaml_test["stream_init"], proto_test->mutable_stream_init()); !status.ok()) return status;
  }
  if (yaml_test["stream_destroy"]) {
    if (absl::Status status = ConvertExpectation(yaml_test["stream_destroy"], proto_test->mutable_stream_destroy()); !status.ok()) return status;
  }
  return absl::OkStatus();
}

absl::Status ConvertInvocation(const YAML::Node& yaml_invocation, Invocation* proto_invocation) {
  if (!yaml_invocation.IsMap()) {
    return absl::InvalidArgumentError("Invocation must be a YAML map");
  }
  if (yaml_invocation["input"]) {
    if (absl::Status status = ConvertInput(yaml_invocation["input"], proto_invocation->mutable_input()); !status.ok()) return status;
  }
  if (yaml_invocation["result"]) {
    if (absl::Status status = ConvertExpectation(yaml_invocation["result"], proto_invocation->mutable_result()); !status.ok()) return status;
  }
  return absl::OkStatus();
}

absl::Status ConvertInput(const YAML::Node& yaml_input, Input* proto_input) {
  if (!yaml_input.IsMap()) {
    return absl::InvalidArgumentError("Input must be a YAML map");
  }
  if (yaml_input["headers"] && yaml_input["headers"].IsSequence()) {
    if (absl::Status status = ConvertHeaders(yaml_input["headers"], proto_input->mutable_header()); !status.ok()) return status;
  }
  if (yaml_input["content"]) {
    proto_input->set_content(GetBytesValue(yaml_input["content"]).value_or(""));
  }
  if (yaml_input["file"]) {
    proto_input->set_file(GetStringValue(yaml_input["file"]).value_or(""));
  }
  return absl::OkStatus();
}

absl::Status ConvertExpectation(const YAML::Node& yaml_expectation, Expectation* proto_expectation) {
  if (!yaml_expectation.IsMap()) {
    return absl::InvalidArgumentError("Expectation must be a YAML map");
  }
  if (yaml_expectation["has_header"] && yaml_expectation["has_header"].IsSequence()) {
    if (absl::Status status = ConvertHeaders(yaml_expectation["has_header"], proto_expectation->mutable_has_header()); !status.ok()) return status;
  }
  if (yaml_expectation["no_header"] && yaml_expectation["no_header"].IsSequence()) {
    if (absl::Status status = ConvertHeaders(yaml_expectation["no_header"], proto_expectation->mutable_no_header()); !status.ok()) return status;
  }
  if (yaml_expectation["headers"] && yaml_expectation["headers"].IsSequence()) {
    if (absl::Status status = ConvertStringMatchers(yaml_expectation["headers"], proto_expectation->mutable_headers()); !status.ok()) return status;
  }
  if (yaml_expectation["body"] && yaml_expectation["body"].IsSequence()) {
    if (absl::Status status = ConvertStringMatchers(yaml_expectation["body"], proto_expectation->mutable_body()); !status.ok()) return status;
  }
  if (yaml_expectation["immediate"]) {
    if (absl::Status status = ConvertImmediate(yaml_expectation["immediate"], proto_expectation->mutable_immediate()); !status.ok()) return status;
  }
  if (yaml_expectation["log"] && yaml_expectation["log"].IsSequence()) {
    if (absl::Status status = ConvertStringMatchers(yaml_expectation["log"], proto_expectation->mutable_log()); !status.ok()) return status;
  }
  return absl::OkStatus();
}

absl::Status ConvertHeader(const YAML::Node& yaml_header, Header* proto_header) {
  if (yaml_header.IsMap()) {
    if (yaml_header["key"]) {
      proto_header->set_key(GetStringValue(yaml_header["key"]).value_or(""));
    }
    if (yaml_header["value"]) {
      proto_header->set_value(GetBytesValue(yaml_header["value"]).value_or(""));
    }
  } else if (yaml_header.IsScalar()) {
    std::string header_str = GetStringValue(yaml_header).value_or("");
    std::vector<std::string> parts = absl::StrSplit(header_str, absl::MaxSplits(':', 1));
    if (parts.size() == 2) {
      proto_header->set_key(parts[0]);
      proto_header->set_value(std::string(absl::StripAsciiWhitespace(parts[1])));
    } else {
      return absl::InvalidArgumentError(absl::StrCat("Invalid header format: ", header_str));
    }
  } else {
    return absl::InvalidArgumentError("Header must be a map or string");
  }
  return absl::OkStatus();
}

absl::Status ConvertStringMatcher(const YAML::Node& yaml_matcher, StringMatcher* proto_matcher) {
  if (!yaml_matcher.IsMap()) {
    return absl::InvalidArgumentError("StringMatcher must be a YAML map");
  }
  proto_matcher->set_invert(GetBoolValue(yaml_matcher["invert"]).value_or(false));
  if (yaml_matcher["exact"]) {
    proto_matcher->set_exact(GetBytesValue(yaml_matcher["exact"]).value_or(""));
  } else if (yaml_matcher["regex"]) {
    proto_matcher->set_regex(GetStringValue(yaml_matcher["regex"]).value_or(""));
  } else if (yaml_matcher["file"]) {
    proto_matcher->set_file(GetStringValue(yaml_matcher["file"]).value_or(""));
  } else {
    return absl::InvalidArgumentError("StringMatcher must have one of: exact, regex, or file");
  }
  return absl::OkStatus();
}

absl::Status ConvertEnv(const YAML::Node& yaml_env, Env* proto_env) {
  if (!yaml_env.IsMap()) {
    return absl::InvalidArgumentError("Env must be a YAML map");
  }
  proto_env->set_test_path(GetStringValue(yaml_env["test_path"]).value_or(""));
  proto_env->set_wasm_path(GetStringValue(yaml_env["wasm_path"]).value_or(""));
  proto_env->set_config_path(GetStringValue(yaml_env["config_path"]).value_or(""));
  proto_env->set_log_path(GetStringValue(yaml_env["log_path"]).value_or(""));

  if (auto level_str = GetStringValue(yaml_env["log_level"])) {
    proto_env->set_log_level(ConvertLogLevel(*level_str));
  }

  if (auto time_secs = GetUInt64Value(yaml_env["time_secs"])) {
    proto_env->set_time_secs(*time_secs);
  }

  if (auto num_streams = GetUInt64Value(yaml_env["num_additional_streams"])) {
    proto_env->set_num_additional_streams(*num_streams);
  }

  if (auto advance_rate = GetUInt64Value(yaml_env["additional_stream_advance_rate"])) {
    proto_env->set_additional_stream_advance_rate(*advance_rate);
  }
  return absl::OkStatus();
}

absl::Status ConvertImmediate(const YAML::Node& yaml_immediate, Expectation::Immediate* proto_immediate) {
  if (!yaml_immediate.IsMap()) {
    return absl::InvalidArgumentError("Immediate must be a YAML map");
  }
  if (auto http_status = GetUInt32Value(yaml_immediate["http_status"])) {
    proto_immediate->set_http_status(*http_status);
  }
  if (auto grpc_status = GetUInt32Value(yaml_immediate["grpc_status"])) {
    proto_immediate->set_grpc_status(*grpc_status);
  }
  if (yaml_immediate["details"]) {
    proto_immediate->set_details(GetStringValue(yaml_immediate["details"]).value_or(""));
  }
  return absl::OkStatus();
}

absl::Status ConvertHeaders(const YAML::Node& yaml_headers, google::protobuf::RepeatedPtrField<Header>* proto_headers) {
  if (!yaml_headers.IsSequence()) {
    return absl::InvalidArgumentError("Headers must be a YAML sequence");
  }
  for (const auto& yaml_header : yaml_headers) {
    Header* proto_header = proto_headers->Add();
    if (absl::Status status = ConvertHeader(yaml_header, proto_header); !status.ok()) return status;
  }
  return absl::OkStatus();
}

absl::Status ConvertStringMatchers(const YAML::Node& yaml_matchers, google::protobuf::RepeatedPtrField<StringMatcher>* proto_matchers) {
  if (!yaml_matchers.IsSequence()) {
    return absl::InvalidArgumentError("StringMatchers must be a YAML sequence");
  }
  for (const auto& yaml_matcher : yaml_matchers) {
    StringMatcher* proto_matcher = proto_matchers->Add();
    if (absl::Status status = ConvertStringMatcher(yaml_matcher, proto_matcher); !status.ok()) return status;
  }
  return absl::OkStatus();
}

absl::Status ConvertInvocations(const YAML::Node& yaml_invocations, google::protobuf::RepeatedPtrField<Invocation>* proto_invocations) {
  if (!yaml_invocations.IsSequence()) {
    return absl::InvalidArgumentError("Invocations must be a YAML sequence");
  }
  for (const auto& yaml_invocation : yaml_invocations) {
    Invocation* proto_invocation = proto_invocations->Add();
    if (absl::Status status = ConvertInvocation(yaml_invocation, proto_invocation); !status.ok()) return status;
  }
  return absl::OkStatus();
}

}  // namespace

absl::StatusOr<TestSuite> ConvertYamlToTestSuite(std::string_view yaml_content) {
  TestSuite test_suite;
  try {
    YAML::Node yaml_root = YAML::Load(std::string(yaml_content));

    if (yaml_root["env"]) {
      if (absl::Status env_status = ConvertEnv(yaml_root["env"], test_suite.mutable_env()); !env_status.ok()) {
        return env_status;
      }
    }

    if (yaml_root["tests"] && yaml_root["tests"].IsSequence()) {
      for (const auto& yaml_test : yaml_root["tests"]) {
        Test* proto_test = test_suite.add_test();
        if (absl::Status test_status = ConvertTest(yaml_test, proto_test); !test_status.ok()) {
          return test_status;
        }
      }
    }
    return test_suite;
  } catch (const YAML::Exception& e) {
    return absl::InvalidArgumentError(absl::StrCat("YAML parsing error: ", e.what()));
  }
}

}  // namespace service_extensions_samples::pb