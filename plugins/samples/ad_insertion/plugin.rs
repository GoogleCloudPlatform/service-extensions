// Copyright 2026 Google LLC
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
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::collections::HashMap;

// Static GPT library URL
const GPT_LIBRARY_URL: &str = "https://securepubads.g.doubleclick.net/tag/js/gpt.js";

proxy_wasm::main! {{
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext::new())
    });
}}

#[derive(Clone)]
struct AdConfig {
    slot: &'static str,     // GAM ad slot path (e.g., "/1234/header_ad")
    size: &'static str,     // Ad dimensions (e.g., "728x90")
    marker: &'static str,   // HTML tag to insert ads relative to
    insert_before: bool,    // Insert before (true) or after (false) the marker
}

struct MyRootContext {
    ad_configs: HashMap<&'static str, AdConfig>,
    inject_gpt_library: bool,
}

impl MyRootContext {
    fn new() -> Self {
        // Ad configuration - set this to be loaded from plugin config
        // Format: {position_name, {gam_slot, ad_size, html_marker, insert_before}}
        let mut ad_configs = HashMap::new();
        ad_configs.insert("header", AdConfig {
            slot: "/1234/header_ad",
            size: "728x90",
            marker: "<body>",
            insert_before: false,
        });
        ad_configs.insert("content", AdConfig {
            slot: "/1234/content_ad",
            size: "300x250",
            marker: "<article>",
            insert_before: false,
        });
        ad_configs.insert("sidebar", AdConfig {
            slot: "/1234/sidebar_ad",
            size: "160x600",
            marker: "</article>",
            insert_before: true,
        });

        Self {
            ad_configs,
            inject_gpt_library: true,
        }
    }
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        true
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            ad_configs: self.ad_configs.clone(),
            inject_gpt_library: self.inject_gpt_library,
            should_insert_ads: false,
            is_ad_request: false,
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    ad_configs: HashMap<&'static str, AdConfig>,
    inject_gpt_library: bool,
    should_insert_ads: bool,
    is_ad_request: bool,
}

impl MyHttpContext {
    fn is_gpt_already_loaded(&self, body: &str) -> bool {
        body.contains("googletag") || 
        body.contains("gpt.js") || 
        body.contains("doubleclick.net/tag/js/gpt")
    }

    fn prepare_gpt_library_injection(&self, body: &str, insertions: &mut Vec<(usize, String)>) {
        if let Some(head_pos) = body.find("<head>") {
            let gpt_script = format!("\n  <script async src=\"{}\"></script>", GPT_LIBRARY_URL);
            insertions.push((head_pos + 6, gpt_script));
            return;
        }

        if let Some(body_pos) = body.find("<body>") {
            let gpt_script = format!("<script async src=\"{}\"></script>\n", GPT_LIBRARY_URL);
            insertions.push((body_pos, gpt_script));
        }
    }

    fn prepare_ad_insertion(
        &self,
        body: &str,
        position: &'static str,
        config: &AdConfig,
        insertions: &mut Vec<(usize, String)>,
    ) {
        if let Some(marker_pos) = body.find(config.marker) {
            let insert_pos = if config.insert_before {
                marker_pos
            } else {
                marker_pos + config.marker.len()
            };
            
            let ad_html = self.generate_gam_ad_html(position, config);
            insertions.push((insert_pos, ad_html));
        }
    }

    fn apply_all_insertions(&self, body: &mut String, insertions: &mut Vec<(usize, String)>) {
        // Sort insertions by position in DESCENDING order
        // This ensures that later insertions don't affect positions of earlier ones
        insertions.sort_by(|a, b| b.0.cmp(&a.0));
        
        // Apply all insertions
        for (pos, content) in insertions {
            body.insert_str(*pos, content);
        }
    }

    fn generate_gam_ad_html(&self, position: &str, config: &AdConfig) -> String {
        format!(
            r#"<div id="ad-container-{position}" class="ad-unit">
  <!-- GAM Ad Slot: {slot} -->
  <script>
    (function() {{
      // Same-domain GAM integration
      var googletag = window.googletag || {{}};
      googletag.cmd = googletag.cmd || [];
      googletag.cmd.push(function() {{
        googletag.defineSlot('{slot}', 
                            [{size}], 
                            'ad-container-{position}').addService(googletag.pubads());
        googletag.pubads().enableSingleRequest();
        googletag.enableServices();
      }});
    }})();
  </script>
  <div id="div-gpt-ad-{position}">
    <script>
      googletag.cmd.push(function() {{ 
        googletag.display('div-gpt-ad-{position}'); 
      }});
    </script>
  </div>
</div>"#,
            position = position,
            slot = config.slot,
            size = config.size
        )
    }

    fn process_body_with_gam(&self, body: &str) -> String {
        let mut modified_body = body.to_string();
        let mut insertions: Vec<(usize, String)> = Vec::new();
        
        // 1. Prepare GPT library injection if needed and not already present
        if self.inject_gpt_library && !self.is_gpt_already_loaded(body) {
            self.prepare_gpt_library_injection(body, &mut insertions);
        }
        
        // 2. Prepare all ad insertions in single pass
        for (position, config) in &self.ad_configs {
            self.prepare_ad_insertion(body, position, config, &mut insertions);
        }
        
        // 3. Apply all insertions in reverse order (to maintain correct indices)
        if !insertions.is_empty() {
            self.apply_all_insertions(&mut modified_body, &mut insertions);
        }

        modified_body
    }
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        // Skip ad insertion for ad requests to avoid infinite loops
        if let Some(path) = self.get_http_request_header(":path") {
            if path.contains("/ads/") {
                self.is_ad_request = true;
            }
        }
        Action::Continue
    }

    fn on_http_response_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        if let Some(content_type) = self.get_http_response_header("Content-Type") {
            if content_type.contains("text/html") {
                self.should_insert_ads = true;
                self.set_http_response_header("Content-Length", None);
            }
        }
        Action::Continue
    }

    fn on_http_response_body(&mut self, body_size: usize, _end_of_stream: bool) -> Action {
        if !self.should_insert_ads || self.is_ad_request {
            return Action::Continue;
        }

        // Process HTML body and inject GAM ads
        if let Some(body_bytes) = self.get_http_response_body(0, body_size) {
            if let Ok(body_str) = std::str::from_utf8(&body_bytes) {
                let modified_body = self.process_body_with_gam(body_str);
                self.set_http_response_body(0, body_size, modified_body.as_bytes());
            }
        }

        Action::Continue
    }
}
// [END serviceextensions_plugin_ad_insertion]
