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

#include <string>
#include <vector>
#include <yaml-cpp/yaml.h>

#include "absl/status/status.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_split.h"
#include "absl/strings/strip.h"
#include "absl/strings/escaping.h"
#include "google/protobuf/struct.pb.h"
#include "google/protobuf/util/json_util.h"

namespace service_extensions_samples::pb {

namespace {

// Forward declaration
google::protobuf::Value ConvertYamlNodeToProtoValue(const YAML::Node& node, const std::string& key = "");

// Normalizes a scalar header string "Key: Value" or "Key" into a Struct Value.
google::protobuf::Value NormalizeHeaderScalar(const std::string& header_str) {
  google::protobuf::Value header_val;
  auto* struct_fields = header_val.mutable_struct_value()->mutable_fields();

  std::vector<std::string> parts = absl::StrSplit(header_str, absl::MaxSplits(':', 1));
  if (parts.size() == 2) {
    (*struct_fields)["key"].set_string_value(parts[0]);
    std::string encoded;
    absl::Base64Escape(std::string(absl::StripAsciiWhitespace(parts[1])), &encoded);
    (*struct_fields)["value"].set_string_value(encoded);
  } else {
    (*struct_fields)["key"].set_string_value(header_str);
    (*struct_fields)["value"].set_string_value("");
  }
  return header_val;
}

google::protobuf::Value ConvertYamlNodeToProtoValue(const YAML::Node& node, const std::string& key) {
  google::protobuf::Value value;
  switch (node.Type()) {
    case YAML::NodeType::Null:
      value.set_null_value(google::protobuf::NULL_VALUE);
      break;
    case YAML::NodeType::Scalar: {
      std::string str_val = node.as<std::string>();
      
      // If this key corresponds to a bytes field in the proto, we must Base64 encode it.
      if (key == "value" || key == "exact" || key == "content") {
        std::string encoded;
        absl::Base64Escape(str_val, &encoded);
        value.set_string_value(encoded);
      } else if (str_val == "true" || str_val == "True" || str_val == "TRUE") {
        value.set_bool_value(true);
      } else if (str_val == "false" || str_val == "False" || str_val == "FALSE") {
        value.set_bool_value(false);
      } else {
        // Try to parse as double
        try {
          size_t idx;
          double d_val = std::stod(str_val, &idx);
          if (idx == str_val.size()) {
            value.set_number_value(d_val);
          } else {
            value.set_string_value(str_val);
          }
        } catch (...) {
          value.set_string_value(str_val);
        }
      }
      break;
    }
    case YAML::NodeType::Sequence: {
      auto* list_values = value.mutable_list_value()->mutable_values();
      for (const auto& it : node) {
        // Normalize headers only if they are written as scalar strings inside header-related lists.
        // Maps are parsed normally (their "value" fields will be Base64 encoded recursively).
        if ((key == "header" || key == "has_header" || key == "no_header") && it.IsScalar()) {
          *list_values->Add() = NormalizeHeaderScalar(it.as<std::string>());
        } else {
          *list_values->Add() = ConvertYamlNodeToProtoValue(it, key);
        }
      }
      break;
    }
    case YAML::NodeType::Map: {
      auto* struct_fields = value.mutable_struct_value()->mutable_fields();
      for (const auto& it : node) {
        std::string child_key = it.first.as<std::string>();
        (*struct_fields)[child_key] = ConvertYamlNodeToProtoValue(it.second, child_key);
      }
      break;
    }
    case YAML::NodeType::Undefined:
      break;
  }
  return value;
}

} // namespace

absl::StatusOr<TestSuite> ConvertYamlToTestSuite(std::string_view yaml_content) {
  try {
    YAML::Node yaml_root = YAML::Load(std::string(yaml_content));
    if (!yaml_root.IsDefined() || yaml_root.IsNull()) {
      return TestSuite();
    }
    if (!yaml_root.IsMap()) {
      return absl::InvalidArgumentError("YAML root must be a map");
    }

    google::protobuf::Value root_value = ConvertYamlNodeToProtoValue(yaml_root);
    if (!root_value.has_struct_value()) {
      return absl::InvalidArgumentError("Failed to convert YAML to proto struct");
    }

    std::string json_string;
    google::protobuf::util::JsonPrintOptions options;
    options.preserve_proto_field_names = true;
    
    auto status = google::protobuf::util::MessageToJsonString(root_value.struct_value(), &json_string, options);
    if (!status.ok()) {
      return absl::InvalidArgumentError(absl::StrCat("Failed to convert proto struct to JSON: ", status.ToString()));
    }

    TestSuite test_suite;
    google::protobuf::util::JsonParseOptions parse_options;
    parse_options.ignore_unknown_fields = false;
    
    status = google::protobuf::util::JsonStringToMessage(json_string, &test_suite, parse_options);
    if (!status.ok()) {
      return absl::InvalidArgumentError(absl::StrCat("Failed to parse JSON to TestSuite: ", status.ToString(), "\nJSON: ", json_string));
    }

    return test_suite;
  } catch (const YAML::Exception& e) {
    return absl::InvalidArgumentError(absl::StrCat("YAML parsing error: ", e.what()));
  } catch (const std::exception& e) {
    return absl::InternalError(absl::StrCat("Internal error: ", e.what()));
  }
}

} // namespace service_extensions_samples::pb