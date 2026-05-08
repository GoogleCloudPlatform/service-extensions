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
#include "google/protobuf/message.h"
#include "google/protobuf/descriptor.h"

namespace service_extensions_samples::pb {

namespace {

absl::Status SetSingularScalarField(const YAML::Node& node, const google::protobuf::FieldDescriptor* field, google::protobuf::Message* message, const google::protobuf::Reflection* reflection) {
  if (!node.IsScalar()) {
    return absl::InvalidArgumentError(absl::StrCat("Expected a Scalar for field '", field->name(), "'"));
  }
  std::string str_val = node.as<std::string>();

  try {
    switch (field->cpp_type()) {
      case google::protobuf::FieldDescriptor::CPPTYPE_INT32:
        reflection->SetInt32(message, field, node.as<int32_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_INT64:
        reflection->SetInt64(message, field, node.as<int64_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_UINT32:
        reflection->SetUInt32(message, field, node.as<uint32_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_UINT64:
        reflection->SetUInt64(message, field, node.as<uint64_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_DOUBLE:
        reflection->SetDouble(message, field, node.as<double>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_FLOAT:
        reflection->SetFloat(message, field, node.as<float>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_BOOL:
        reflection->SetBool(message, field, node.as<bool>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_STRING:
        reflection->SetString(message, field, str_val);
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_ENUM: {
        const google::protobuf::EnumValueDescriptor* ev = nullptr;
        ev = field->enum_type()->FindValueByName(str_val);
        if (!ev) {
          try {
            int enum_num = node.as<int>();
            ev = field->enum_type()->FindValueByNumber(enum_num);
          } catch (...) {}
        }
        if (!ev) {
          return absl::InvalidArgumentError(absl::StrCat("Invalid enum value '", str_val, "' for field '", field->name(), "'"));
        }
        reflection->SetEnum(message, field, ev);
        break;
      }
      default:
        return absl::UnimplementedError(absl::StrCat("Unsupported type for field '", field->name(), "'"));
    }
  } catch (const YAML::Exception& e) {
    return absl::InvalidArgumentError(absl::StrCat("Failed to parse field '", field->name(), "': ", e.what()));
  }
  return absl::OkStatus();
}

absl::Status AddRepeatedScalarField(const YAML::Node& node, const google::protobuf::FieldDescriptor* field, google::protobuf::Message* message, const google::protobuf::Reflection* reflection) {
  if (!node.IsScalar()) {
    return absl::InvalidArgumentError(absl::StrCat("Expected a Scalar for repeated field '", field->name(), "'"));
  }
  std::string str_val = node.as<std::string>();

  try {
    switch (field->cpp_type()) {
      case google::protobuf::FieldDescriptor::CPPTYPE_INT32:
        reflection->AddInt32(message, field, node.as<int32_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_INT64:
        reflection->AddInt64(message, field, node.as<int64_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_UINT32:
        reflection->AddUInt32(message, field, node.as<uint32_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_UINT64:
        reflection->AddUInt64(message, field, node.as<uint64_t>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_DOUBLE:
        reflection->AddDouble(message, field, node.as<double>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_FLOAT:
        reflection->AddFloat(message, field, node.as<float>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_BOOL:
        reflection->AddBool(message, field, node.as<bool>());
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_STRING:
        reflection->AddString(message, field, str_val);
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_ENUM: {
        const google::protobuf::EnumValueDescriptor* ev = nullptr;
        ev = field->enum_type()->FindValueByName(str_val);
        if (!ev) {
          try {
            int enum_num = node.as<int>();
            ev = field->enum_type()->FindValueByNumber(enum_num);
          } catch (...) {}
        }
        if (!ev) {
          return absl::InvalidArgumentError(absl::StrCat("Invalid enum value '", str_val, "' for repeated field '", field->name(), "'"));
        }
        reflection->AddEnum(message, field, ev);
        break;
      }
      default:
        return absl::UnimplementedError(absl::StrCat("Unsupported type for repeated field '", field->name(), "'"));
    }
  } catch (const YAML::Exception& e) {
    return absl::InvalidArgumentError(absl::StrCat("Failed to parse repeated field '", field->name(), "': ", e.what()));
  }
  return absl::OkStatus();
}

absl::Status ConvertYamlToProtoMessage(const YAML::Node& node, google::protobuf::Message* message) {
  if (!node.IsMap()) {
    return absl::InvalidArgumentError(absl::StrCat("Expected a Map for message ", message->GetDescriptor()->name(), " but got ", node.Type()));
  }

  const google::protobuf::Descriptor* descriptor = message->GetDescriptor();
  const google::protobuf::Reflection* reflection = message->GetReflection();

  for (const auto& it : node) {
    std::string key = it.first.as<std::string>();
    const google::protobuf::FieldDescriptor* field = descriptor->FindFieldByName(key);
    if (!field) {
      return absl::InvalidArgumentError(absl::StrCat("Field '", key, "' is not found in the ", descriptor->name(), " proto"));
    }

    const YAML::Node& value_node = it.second;
    if (field->is_repeated()) {
      if (!value_node.IsSequence()) {
        return absl::InvalidArgumentError(absl::StrCat("Expected a Sequence for repeated field '", key, "'"));
      }
      for (const auto& elem : value_node) {
        if (field->cpp_type() == google::protobuf::FieldDescriptor::CPPTYPE_MESSAGE) {
          google::protobuf::Message* nested_message = reflection->AddMessage(message, field);
          if (absl::Status status = ConvertYamlToProtoMessage(elem, nested_message); !status.ok()) {
            return status;
          }
        } else {
          if (absl::Status status = AddRepeatedScalarField(elem, field, message, reflection); !status.ok()) {
            return status;
          }
        }
      }
    } else {
      if (field->cpp_type() == google::protobuf::FieldDescriptor::CPPTYPE_MESSAGE) {
        google::protobuf::Message* nested_message = reflection->MutableMessage(message, field);
        if (absl::Status status = ConvertYamlToProtoMessage(value_node, nested_message); !status.ok()) {
          return status;
        }
      } else {
        if (absl::Status status = SetSingularScalarField(value_node, field, message, reflection); !status.ok()) {
          return status;
        }
      }
    }
  }
  return absl::OkStatus();
}

} // namespace

absl::StatusOr<TestSuite> ConvertYamlToTestSuite(std::string_view yaml_content) {
  try {
    YAML::Node yaml_root = YAML::Load(std::string(yaml_content));
    if (!yaml_root.IsDefined() || yaml_root.IsNull()) {
      return TestSuite();
    }
    TestSuite test_suite;
    if (absl::Status status = ConvertYamlToProtoMessage(yaml_root, &test_suite); !status.ok()) {
      return absl::Status(status.code(), absl::StrCat("Failed to parse input YAML: ", status.message()));
    }
    return test_suite;
  } catch (const YAML::Exception& e) {
    return absl::InvalidArgumentError(absl::StrCat("YAML parsing error: ", e.what()));
  } catch (const std::exception& e) {
    return absl::InternalError(absl::StrCat("Internal error: ", e.what()));
  }
}

} // namespace service_extensions_samples::pb