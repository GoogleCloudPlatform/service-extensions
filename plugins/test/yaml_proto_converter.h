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

#include <string_view>
#include "absl/status/statusor.h"
#include "test/runner.pb.h"

namespace service_extensions_samples::pb {

// Converts a YAML string defining a test suite into a TestSuite proto.
// Returns a status error if the YAML is invalid or cannot be parsed.
absl::StatusOr<TestSuite> ConvertYamlToTestSuite(std::string_view yaml_content);

}  // namespace service_extensions_samples::pb