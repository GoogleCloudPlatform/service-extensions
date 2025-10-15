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
#include <fstream>
#include <sstream>

#include "absl/strings/ascii.h"
#include "absl/strings/str_cat.h"

namespace service_extensions_samples::pb {

// Helper function implementations
std::string YamlProtoConverter::GetStringValue(const YAML::Node& node, const std::string& default_value) {
  if (!node.IsDefined() || node.IsNull()) {
    return default_value;
  }
  return node.as<std::string>(default_value);
}

int32_t YamlProtoConverter::GetIntValue(const YAML::Node& node, int32_t default_value) {
  if (!node.IsDefined() || node.IsNull()) {
    return default_value;
  }
  return node.as<int32_t>(default_value);
}

int64_t YamlProtoConverter::GetInt64Value(const YAML::Node& node, int64_t default_value) {
  if (!node.IsDefined() || node.IsNull()) {
    return default_value;
  }
  return node.as<int64_t>(default_value);
}

uint32_t YamlProtoConverter::GetUInt32Value(const YAML::Node& node, uint32_t default_value) {
  if (!node.IsDefined() || node.IsNull()) {
    return default_value;
  }
  return node.as<uint32_t>(default_value);
}

uint64_t YamlProtoConverter::GetUInt64Value(const YAML::Node& node, uint64_t default_value) {
  if (!node.IsDefined() || node.IsNull()) {
    return default_value;
  }
  return node.as<uint64_t>(default_value);
}

bool YamlProtoConverter::GetBoolValue(const YAML::Node& node, bool default_value) {
  if (!node.IsDefined() || node.IsNull()) {
    return default_value;
  }
  return node.as<bool>(default_value);
}

std::string YamlProtoConverter::GetBytesValue(const YAML::Node& node, const std::string& default_value) {
  // For bytes fields, we can accept either string or binary data
  if (!node.IsDefined() || node.IsNull()) {
    return default_value;
  }
  return node.as<std::string>(default_value);
}

Env::LogLevel YamlProtoConverter::ConvertLogLevel(const std::string& level_str) {
  std::string upper_level = absl::AsciiStrToUpper(level_str);

  if (upper_level == "TRACE") return Env::TRACE;
  if (upper_level == "DEBUG") return Env::DEBUG;
  if (upper_level == "INFO") return Env::INFO;
  if (upper_level == "WARN") return Env::WARN;
  if (upper_level == "ERROR") return Env::ERROR;
  if (upper_level == "CRITICAL") return Env::CRITICAL;

  return Env::UNDEFINED;
}

// Main conversion functions
absl::StatusOr<TestSuite> YamlProtoConverter::ConvertYamlToTestSuite(const std::string& yaml_content) {
  try {
    YAML::Node yaml_root = YAML::Load(yaml_content);

    TestSuite test_suite;

    // Convert environment
    if (yaml_root["env"]) {
      auto env_status = ConvertEnv(yaml_root["env"], test_suite.mutable_env());
      if (!env_status.ok()) {
        return env_status;
      }
    }

    // Convert tests
    if (yaml_root["tests"] && yaml_root["tests"].IsSequence()) {
      for (const auto& yaml_test : yaml_root["tests"]) {
        Test* proto_test = test_suite.add_test();
        auto test_status = ConvertTest(yaml_test, proto_test);
        if (!test_status.ok()) {
          return test_status;
        }
      }
    }

    return test_suite;
  } catch (const YAML::Exception& e) {
    return absl::InvalidArgumentError(absl::StrCat("YAML parsing error: ", e.what()));
  }
}

absl::Status YamlProtoConverter::ConvertTest(const YAML::Node& yaml_test, Test* proto_test) {
  if (!yaml_test.IsMap()) {
    return absl::InvalidArgumentError("Test must be a YAML map");
  }

  // Set name
  proto_test->set_name(GetStringValue(yaml_test["name"]));

  // Set benchmark flag
  proto_test->set_benchmark(GetBoolValue(yaml_test["benchmark"], false));

  // Handle body chunking plan
  if (yaml_test["body_chunking_plan"]) {
    const auto& chunking_plan = yaml_test["body_chunking_plan"];
    if (chunking_plan["num_chunks"]) {
      proto_test->set_num_chunks(GetIntValue(chunking_plan["num_chunks"]));
    } else if (chunking_plan["chunk_size"]) {
      proto_test->set_chunk_size(GetInt64Value(chunking_plan["chunk_size"]));
    }
  }

  // Convert invocations
  if (yaml_test["request_headers"]) {
    auto status = ConvertInvocation(yaml_test["request_headers"], proto_test->mutable_request_headers());
    if (!status.ok()) return status;
  }

  if (yaml_test["request_body"] && yaml_test["request_body"].IsSequence()) {
    auto status = ConvertInvocations(yaml_test["request_body"], proto_test->mutable_request_body());
    if (!status.ok()) return status;
  }

  if (yaml_test["response_headers"]) {
    auto status = ConvertInvocation(yaml_test["response_headers"], proto_test->mutable_response_headers());
    if (!status.ok()) return status;
  }

  if (yaml_test["response_body"] && yaml_test["response_body"].IsSequence()) {
    auto status = ConvertInvocations(yaml_test["response_body"], proto_test->mutable_response_body());
    if (!status.ok()) return status;
  }

  // Convert lifecycle expectations
  if (yaml_test["plugin_init"]) {
    auto status = ConvertExpectation(yaml_test["plugin_init"], proto_test->mutable_plugin_init());
    if (!status.ok()) return status;
  }

  if (yaml_test["stream_init"]) {
    auto status = ConvertExpectation(yaml_test["stream_init"], proto_test->mutable_stream_init());
    if (!status.ok()) return status;
  }

  if (yaml_test["stream_destroy"]) {
    auto status = ConvertExpectation(yaml_test["stream_destroy"], proto_test->mutable_stream_destroy());
    if (!status.ok()) return status;
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertInvocation(const YAML::Node& yaml_invocation, Invocation* proto_invocation) {
  if (!yaml_invocation.IsMap()) {
    return absl::InvalidArgumentError("Invocation must be a YAML map");
  }

  // Convert input
  if (yaml_invocation["input"]) {
    auto status = ConvertInput(yaml_invocation["input"], proto_invocation->mutable_input());
    if (!status.ok()) return status;
  }

  // Convert result expectation
  if (yaml_invocation["result"]) {
    auto status = ConvertExpectation(yaml_invocation["result"], proto_invocation->mutable_result());
    if (!status.ok()) return status;
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertInput(const YAML::Node& yaml_input, Input* proto_input) {
  if (!yaml_input.IsMap()) {
    return absl::InvalidArgumentError("Input must be a YAML map");
  }

  // Convert headers
  if (yaml_input["headers"] && yaml_input["headers"].IsSequence()) {
    auto status = ConvertHeaders(yaml_input["headers"], proto_input->mutable_header());
    if (!status.ok()) return status;
  }

  // Convert content
  if (yaml_input["content"]) {
    proto_input->set_content(GetBytesValue(yaml_input["content"]));
  }

  // Convert file
  if (yaml_input["file"]) {
    proto_input->set_file(GetStringValue(yaml_input["file"]));
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertExpectation(const YAML::Node& yaml_expectation, Expectation* proto_expectation) {
  if (!yaml_expectation.IsMap()) {
    return absl::InvalidArgumentError("Expectation must be a YAML map");
  }

  // Convert has_header
  if (yaml_expectation["has_header"] && yaml_expectation["has_header"].IsSequence()) {
    auto status = ConvertHeaders(yaml_expectation["has_header"], proto_expectation->mutable_has_header());
    if (!status.ok()) return status;
  }

  // Convert no_header
  if (yaml_expectation["no_header"] && yaml_expectation["no_header"].IsSequence()) {
    auto status = ConvertHeaders(yaml_expectation["no_header"], proto_expectation->mutable_no_header());
    if (!status.ok()) return status;
  }

  // Convert headers matchers
  if (yaml_expectation["headers"] && yaml_expectation["headers"].IsSequence()) {
    auto status = ConvertStringMatchers(yaml_expectation["headers"], proto_expectation->mutable_headers());
    if (!status.ok()) return status;
  }

  // Convert body matchers
  if (yaml_expectation["body"] && yaml_expectation["body"].IsSequence()) {
    auto status = ConvertStringMatchers(yaml_expectation["body"], proto_expectation->mutable_body());
    if (!status.ok()) return status;
  }

  // Convert immediate response
  if (yaml_expectation["immediate"]) {
    auto status = ConvertImmediate(yaml_expectation["immediate"], proto_expectation->mutable_immediate());
    if (!status.ok()) return status;
  }

  // Convert log matchers
  if (yaml_expectation["log"] && yaml_expectation["log"].IsSequence()) {
    auto status = ConvertStringMatchers(yaml_expectation["log"], proto_expectation->mutable_log());
    if (!status.ok()) return status;
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertHeader(const YAML::Node& yaml_header, Header* proto_header) {
  if (yaml_header.IsMap()) {
    // Header as key-value map
    if (yaml_header["key"]) {
      proto_header->set_key(GetStringValue(yaml_header["key"]));
    }
    if (yaml_header["value"]) {
      proto_header->set_value(GetBytesValue(yaml_header["value"]));
    }
  } else if (yaml_header.IsScalar()) {
    // Header as "key: value" string
    std::string header_str = yaml_header.as<std::string>();
    size_t colon_pos = header_str.find(':');
    if (colon_pos != std::string::npos) {
      proto_header->set_key(header_str.substr(0, colon_pos));
      std::string value = header_str.substr(colon_pos + 1);
      // Trim whitespace
      value.erase(0, value.find_first_not_of(" \t"));
      value.erase(value.find_last_not_of(" \t") + 1);
      proto_header->set_value(value);
    } else {
      return absl::InvalidArgumentError(absl::StrCat("Invalid header format: ", header_str));
    }
  } else {
    return absl::InvalidArgumentError("Header must be a map or string");
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertStringMatcher(const YAML::Node& yaml_matcher, StringMatcher* proto_matcher) {
  if (!yaml_matcher.IsMap()) {
    return absl::InvalidArgumentError("StringMatcher must be a YAML map");
  }

  // Set invert flag
  proto_matcher->set_invert(GetBoolValue(yaml_matcher["invert"], false));

  // Set matcher type (only one should be set)
  if (yaml_matcher["exact"]) {
    proto_matcher->set_exact(GetBytesValue(yaml_matcher["exact"]));
  } else if (yaml_matcher["regex"]) {
    proto_matcher->set_regex(GetStringValue(yaml_matcher["regex"]));
  } else if (yaml_matcher["file"]) {
    proto_matcher->set_file(GetStringValue(yaml_matcher["file"]));
  } else {
    return absl::InvalidArgumentError("StringMatcher must have one of: exact, regex, or file");
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertEnv(const YAML::Node& yaml_env, Env* proto_env) {
  if (!yaml_env.IsMap()) {
    return absl::InvalidArgumentError("Env must be a YAML map");
  }

  // Set environment fields
  proto_env->set_test_path(GetStringValue(yaml_env["test_path"]));
  proto_env->set_wasm_path(GetStringValue(yaml_env["wasm_path"]));
  proto_env->set_config_path(GetStringValue(yaml_env["config_path"]));
  proto_env->set_log_path(GetStringValue(yaml_env["log_path"]));

  // Set log level
  if (yaml_env["log_level"]) {
    proto_env->set_log_level(ConvertLogLevel(GetStringValue(yaml_env["log_level"])));
  }

  // Set optional fields
  if (yaml_env["time_secs"]) {
    proto_env->set_time_secs(GetUInt64Value(yaml_env["time_secs"]));
  }

  if (yaml_env["num_additional_streams"]) {
    proto_env->set_num_additional_streams(GetUInt64Value(yaml_env["num_additional_streams"]));
  }

  if (yaml_env["additional_stream_advance_rate"]) {
    proto_env->set_additional_stream_advance_rate(GetUInt64Value(yaml_env["additional_stream_advance_rate"]));
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertImmediate(const YAML::Node& yaml_immediate, Expectation::Immediate* proto_immediate) {
  if (!yaml_immediate.IsMap()) {
    return absl::InvalidArgumentError("Immediate must be a YAML map");
  }

  // Set HTTP status
  if (yaml_immediate["http_status"]) {
    proto_immediate->set_http_status(GetUInt32Value(yaml_immediate["http_status"]));
  }

  // Set gRPC status
  if (yaml_immediate["grpc_status"]) {
    proto_immediate->set_grpc_status(GetUInt32Value(yaml_immediate["grpc_status"]));
  }

  // Set details
  if (yaml_immediate["details"]) {
    proto_immediate->set_details(GetStringValue(yaml_immediate["details"]));
  }

  return absl::OkStatus();
}

// Array conversion helper functions
absl::Status YamlProtoConverter::ConvertHeaders(const YAML::Node& yaml_headers,
                                               google::protobuf::RepeatedPtrField<Header>* proto_headers) {
  if (!yaml_headers.IsSequence()) {
    return absl::InvalidArgumentError("Headers must be a YAML sequence");
  }

  for (const auto& yaml_header : yaml_headers) {
    Header* proto_header = proto_headers->Add();
    auto status = ConvertHeader(yaml_header, proto_header);
    if (!status.ok()) return status;
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertStringMatchers(const YAML::Node& yaml_matchers,
                                                     google::protobuf::RepeatedPtrField<StringMatcher>* proto_matchers) {
  if (!yaml_matchers.IsSequence()) {
    return absl::InvalidArgumentError("StringMatchers must be a YAML sequence");
  }

  for (const auto& yaml_matcher : yaml_matchers) {
    StringMatcher* proto_matcher = proto_matchers->Add();
    auto status = ConvertStringMatcher(yaml_matcher, proto_matcher);
    if (!status.ok()) return status;
  }

  return absl::OkStatus();
}

absl::Status YamlProtoConverter::ConvertInvocations(const YAML::Node& yaml_invocations,
                                                  google::protobuf::RepeatedPtrField<Invocation>* proto_invocations) {
  if (!yaml_invocations.IsSequence()) {
    return absl::InvalidArgumentError("Invocations must be a YAML sequence");
  }

  for (const auto& yaml_invocation : yaml_invocations) {
    Invocation* proto_invocation = proto_invocations->Add();
    auto status = ConvertInvocation(yaml_invocation, proto_invocation);
    if (!status.ok()) return status;
  }

  return absl::OkStatus();
}

}  // namespace service_extensions_samples::pb
