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

// [START serviceextensions_plugin_ad_insertion]
#include <map>
#include <string>
#include <sstream>
#include <string_view>
#include <vector>
#include <algorithm>
#include "proxy_wasm_intrinsics.h"

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t configuration_size) override {
    // Ad configuration - set this to be loaded from plugin config
    // Format: {position_name, {gam_slot, ad_size, html_marker, insert_before}}
    ad_configs_ = {
        {"header", {"/1234/header_ad", "728x90", "<body>", false}},
        {"content", {"/1234/content_ad", "300x250", "<article>", false}},
        {"sidebar", {"/1234/sidebar_ad", "160x600", "</article>", true}}
    };
    
    // GPT library configuration
    gpt_library_url_ = "https://securepubads.g.doubleclick.net/tag/js/gpt.js";
    inject_gpt_library_ = true;
    
    return true;
  }

  struct AdConfig {
    std::string slot;      // GAM ad slot path (e.g., "/1234/header_ad")
    std::string size;      // Ad dimensions (e.g., "728x90")
    std::string marker;    // HTML tag to insert ads relative to
    bool insert_before;    // Insert before (true) or after (false) the marker
  };

  const AdConfig* getAdConfig(std::string_view position) const {
    for (const auto& [key, config] : ad_configs_) {
      if (key == position) return &config;
    }
    return nullptr;
  }

  const std::map<std::string, AdConfig>& getAllAdConfigs() const {
    return ad_configs_;
  }

  const std::string& getGptLibraryUrl() const { return gpt_library_url_; }
  bool shouldInjectGpt() const { return inject_gpt_library_; }

 private:
  std::map<std::string, AdConfig> ad_configs_;
  std::string gpt_library_url_;
  bool inject_gpt_library_;
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root), root_(static_cast<const MyRootContext*>(root)) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Skip ad insertion for ad requests to avoid infinite loops
    auto path = getRequestHeader(":path");
    if (path && path->view().find("/ads/") != std::string::npos) {
      is_ad_request_ = true;
    }
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    auto content_type = getResponseHeader("Content-Type");
    if (content_type && content_type->view().find("text/html") != std::string::npos) {
      should_insert_ads_ = true;
      removeResponseHeader("Content-Length");
    }
    return FilterHeadersStatus::Continue;
  }

  FilterDataStatus onResponseBody(size_t body_size, bool end_of_stream) override {
    if (!should_insert_ads_ || is_ad_request_) {
      return FilterDataStatus::Continue;
    }

    // Process HTML body and inject GAM ads
    auto body = getBufferBytes(WasmBufferType::HttpResponseBody, 0, body_size);
    std::string body_str = std::string(body->view());
    processBodyWithGAM(body_str);

    return FilterDataStatus::Continue;
  }

 private:
  bool isGptAlreadyLoaded(const std::string& body) const {
    return body.find("googletag") != std::string::npos ||
           body.find("gpt.js") != std::string::npos ||
           body.find("doubleclick.net/tag/js/gpt") != std::string::npos;
  }

  void processBodyWithGAM(std::string& body) {
    // Vector to store all insertions: (position, content)
    std::vector<std::pair<size_t, std::string>> insertions;
    
    // 1. Prepare GPT library injection if needed and not already present
    if (root_->shouldInjectGpt() && !isGptAlreadyLoaded(body)) {
      prepareGptLibraryInjection(body, insertions);
    }
    
    // 2. Prepare all ad insertions in single pass
    const auto& ad_configs = root_->getAllAdConfigs();
    for (const auto& [position, config] : ad_configs) {
      prepareAdInsertion(body, position, config, insertions);
    }
    
    // 3. Apply all insertions in reverse order (to maintain correct indices)
    if (!insertions.empty()) {
      applyAllInsertions(body, insertions);
    }

    setBuffer(WasmBufferType::HttpResponseBody, 0, body.size(), body);
  }

  void prepareGptLibraryInjection(std::string& body, 
                                std::vector<std::pair<size_t, std::string>>& insertions) {
    size_t head_pos = body.find("<head>");
    if (head_pos != std::string::npos) {
      insertions.emplace_back(head_pos + 6, 
        "\n  <script async src=\"" + root_->getGptLibraryUrl() + "\"></script>");
      return;
    }

    size_t body_pos = body.find("<body>");
    if (body_pos != std::string::npos) {
      insertions.emplace_back(body_pos, 
        "<script async src=\"" + root_->getGptLibraryUrl() + "\"></script>\n");
    }
  }

  void prepareAdInsertion(std::string& body, std::string_view position,
                         const MyRootContext::AdConfig& config,
                         std::vector<std::pair<size_t, std::string>>& insertions) {
    size_t marker_pos = body.find(config.marker);
    if (marker_pos == std::string::npos) return;

    size_t insert_pos = config.insert_before ? marker_pos : marker_pos + config.marker.length();
    std::string ad_html = generateGAMAdHTML(position, config);
    
    insertions.emplace_back(insert_pos, ad_html);
  }

  void applyAllInsertions(std::string& body, 
                         std::vector<std::pair<size_t, std::string>>& insertions) {
    // Sort insertions by position in DESCENDING order
    // This ensures that later insertions don't affect positions of earlier ones
    std::sort(insertions.begin(), insertions.end(),
              [](const auto& a, const auto& b) {
                return a.first > b.first;
              });
    
    // Apply all insertions
    for (const auto& [pos, content] : insertions) {
      body.insert(pos, content);
    }
  }

  std::string generateGAMAdHTML(std::string_view position, 
                                const MyRootContext::AdConfig& config) const {
    std::ostringstream html;
    
    // GAM Ad HTML Template
    html << "<div id=\"ad-container-" << position << "\" class=\"ad-unit\">\n"
         << "  <!-- GAM Ad Slot: " << config.slot << " -->\n"
         << "  <script>\n"
         << "    (function() {\n"
         << "      // Same-domain GAM integration\n"
         << "      var googletag = window.googletag || {};\n"
         << "      googletag.cmd = googletag.cmd || [];\n"
         << "      googletag.cmd.push(function() {\n"
         << "        googletag.defineSlot('" << config.slot << "', \n"
         << "                            [" << config.size << "], \n"
         << "                            'ad-container-" << position << "').addService(googletag.pubads());\n"
         << "        googletag.pubads().enableSingleRequest();\n"
         << "        googletag.enableServices();\n"
         << "      });\n"
         << "    })();\n"
         << "  </script>\n"
         << "  <div id=\"div-gpt-ad-" << position << "\">\n"
         << "    <script>\n"
         << "      googletag.cmd.push(function() { \n"
         << "        googletag.display('div-gpt-ad-" << position << "'); \n"
         << "      });\n"
         << "    </script>\n"
         << "  </div>\n"
         << "</div>";
    
    return html.str();
  }

  const MyRootContext* root_;
  bool should_insert_ads_ = false;
  bool is_ad_request_ = false;
};

static RegisterContextFactory register_MyHttpContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_ad_insertion]
