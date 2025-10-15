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

#pragma once

#include <string>
#include <yaml-cpp/yaml.h>
#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "test/runner.pb.h"

namespace service_extensions_samples::pb {

class YamlProtoConverter {
 public:
  // Convert YAML content to TestSuite proto
  static absl::StatusOr<TestSuite> ConvertYamlToTestSuite(const std::string& yaml_content);

  // Convert individual YAML node to Test proto
  static absl::Status ConvertTest(const YAML::Node& yaml_test, Test* proto_test);

  // Convert YAML node to Invocation proto
  static absl::Status ConvertInvocation(const YAML::Node& yaml_invocation, Invocation* proto_invocation);

  // Convert YAML node to Input proto
  static absl::Status ConvertInput(const YAML::Node& yaml_input, Input* proto_input);

  // Convert YAML node to Expectation proto
  static absl::Status ConvertExpectation(const YAML::Node& yaml_expectation, Expectation* proto_expectation);

  // Convert YAML node to Header proto
  static absl::Status ConvertHeader(const YAML::Node& yaml_header, Header* proto_header);

  // Convert YAML node to StringMatcher proto
  static absl::Status ConvertStringMatcher(const YAML::Node& yaml_matcher, StringMatcher* proto_matcher);

  // Convert YAML node to Env proto
  static absl::Status ConvertEnv(const YAML::Node& yaml_env, Env* proto_env);

  // Convert YAML node to Immediate proto
  static absl::Status ConvertImmediate(const YAML::Node& yaml_immediate, Expectation::Immediate* proto_immediate);

 private:
  // Helper functions
  static std::string GetStringValue(const YAML::Node& node, const std::string& default_value = "");
  static int32_t GetIntValue(const YAML::Node& node, int32_t default_value = 0);
  static int64_t GetInt64Value(const YAML::Node& node, int64_t default_value = 0);
  static uint32_t GetUInt32Value(const YAML::Node& node, uint32_t default_value = 0);
  static uint64_t GetUInt64Value(const YAML::Node& node, uint64_t default_value = 0);
  static bool GetBoolValue(const YAML::Node& node, bool default_value = false);
  static std::string GetBytesValue(const YAML::Node& node, const std::string& default_value = "");

  // Convert string to LogLevel enum
  static Env::LogLevel ConvertLogLevel(const std::string& level_str);

  // Convert headers from YAML array
  static absl::Status ConvertHeaders(const YAML::Node& yaml_headers,
                                   google::protobuf::RepeatedPtrField<Header>* proto_headers);

  // Convert string matchers from YAML array
  static absl::Status ConvertStringMatchers(const YAML::Node& yaml_matchers,
                                          google::protobuf::RepeatedPtrField<StringMatcher>* proto_matchers);

  // Convert invocations from YAML array
  static absl::Status ConvertInvocations(const YAML::Node& yaml_invocations,
                                        google::protobuf::RepeatedPtrField<Invocation>* proto_invocations);
};

}  // namespace service_extensions_samples::pb
