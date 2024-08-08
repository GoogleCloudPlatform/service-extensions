// Copyright 2024 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// [START serviceextensions_plugin_normalize_header]
#include "proxy_wasm_intrinsics.h"

// Determines the device type from the "Host" header and
// adds a "client-device-type" header accordingly.
class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    const auto host = getRequestHeader("Host");
    if (host) {
      const auto host_value = host->toString();
      const auto device_type = getDeviceType(host_value);
      addRequestHeader("client-device-type", device_type);
    }

    return FilterHeadersStatus::Continue;
  }

 private:
  // Helper function to determine the device type based on the host value
  std::string_view getDeviceType(std::string_view host_value) {
    // Check if the host value indicates a mobile device
    if (host_value.find("m.example.com") != std::string::npos) {
      return "mobile";
    }
    // Check if the host value indicates a tablet device
    else if (host_value.find("t.example.com") != std::string::npos) {
      return "tablet";
    }
    // Default to "desktop" if no specific device type is identified
    return "desktop";
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_normalize_header]
