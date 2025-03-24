// Copyright 2025 Google LLC
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

// [START serviceextensions_plugin_redirect_bulk]
#include "proxy_wasm_intrinsics.h"
#include "absl/strings/ascii.h"
#include "absl/strings/str_split.h"
#include "absl/strings/str_cat.h"
#include <unordered_map>
#include <string>

// Root context class that handles plugin configuration and domain mappings.
class MyRootContext : public RootContext {
public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  // Called when the plugin is configured with the provided configuration.
  bool onConfigure(size_t config_len) override {
    // Retrieve the plugin configuration data.
    auto config_data = getBufferBytes(WasmBufferType::PluginConfiguration, 0, config_len);
    
    // If no configuration is provided, log a warning and continue.
    if (!config_data || config_data->size() == 0) {
      LOG_WARN("No configuration provided, no redirects will be performed");
      return true;
    }

    // Convert the configuration data to a string.
    std::string config_str = config_data->toString();
    // Split the configuration string into lines.
    std::vector<std::string> lines = absl::StrSplit(config_str, '\n');

    // Parse each line to extract domain mappings.
    for (const auto& line : lines) {
      // Strip whitespace and skip empty lines or comments.
      absl::string_view stripped = absl::StripAsciiWhitespace(line);
      if (stripped.empty() || stripped[0] == '#') continue;

      // Split the line into source and target domains.
      std::vector<absl::string_view> parts = 
          absl::StrSplit(stripped, absl::MaxSplits(' ', 1));
          
      // Ensure the line has exactly two parts (source and target domains).
      if (parts.size() != 2) {
        LOG_WARN("Invalid mapping format: " + std::string(stripped));
        continue;
      }

      // Convert the source domain to lowercase for case-insensitive matching.
      std::string source = absl::AsciiStrToLower(parts[0]);
      // Store the mapping in the domain_mappings_ map.
      domain_mappings_[source] = std::string(parts[1]);
    }

    // Log the number of domain mappings loaded.
    LOG_INFO(absl::StrCat("Loaded ", domain_mappings_.size(), " domain mappings"));
    return true;
  }

  // Map to store domain mappings (source domain -> target domain).
  std::unordered_map<std::string, std::string> domain_mappings_;
};

// HTTP context class that handles incoming HTTP requests.
class MyHttpContext : public Context {
public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<const MyRootContext*>(root)) {}

  // Called when HTTP request headers are received.
  FilterHeadersStatus onRequestHeaders(uint32_t, bool) override {
    // Get the ":authority" header which contains the hostname.
    auto authority = getRequestHeader(":authority");
    if (!authority) return FilterHeadersStatus::Continue;

    // Extract the domain part (remove port if present).
    absl::string_view host_view = authority->view();
    size_t colon_pos = host_view.find(':');
    std::string domain = absl::AsciiStrToLower(host_view.substr(0, colon_pos));

    // Check if the domain should be redirected.
    auto it = root_->domain_mappings_.find(domain);
    if (it == root_->domain_mappings_.end()) {
      return FilterHeadersStatus::Continue;
    }

    // Get the request path.
    std::string path = "/";
    if (auto path_header = getRequestHeader(":path")) {
      path = path_header->toString();
    }

    // Get the request scheme (http or https).
    std::string scheme = "https";
    if (auto scheme_header = getRequestHeader(":scheme")) {
      scheme = scheme_header->toString();
    }

    // Construct the new URL.
    const std::string new_url = absl::StrCat(
        scheme, "://", it->second, path);
    
    // Send a 301 redirect response with the new location.
    sendLocalResponse(301, "", "Redirecting to " + new_url,
                     {{"Location", new_url}});
    return FilterHeadersStatus::ContinueAndEndStream;
  }

private:
  // Pointer to the root context containing domain mappings.
  const MyRootContext* root_;
};

// Register the context factories for the plugin.
static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_redirect_bulk]