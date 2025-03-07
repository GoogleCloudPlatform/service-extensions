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

// [START serviceextensions_plugin_redirect]
use log::*;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::collections::HashMap;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext {
            domain_mappings: Rc::new(HashMap::new()),
        })
    });
}}

struct MyRootContext {
    domain_mappings: Rc<HashMap<String, String>>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        if let Some(config) = self.get_plugin_configuration() {
            match String::from_utf8(config) {
                Ok(config_str) => {
                    let mut mappings = HashMap::new();

                    // Parse each line as "source_domain target_domain"
                    for line in config_str.lines() {
                        let line = line.trim();
                        if line.is_empty() || line.starts_with('#') {
                            continue; // Skip empty lines and comments
                        }

                        let parts: Vec<&str> = line.split_whitespace().collect();
                        if parts.len() == 2 {
                            mappings.insert(parts[0].to_string(), parts[1].to_string());
                        } else {
                            warn!("Invalid mapping format: {}", line);
                        }
                    }

                    self.domain_mappings = Rc::new(mappings);
                    info!("Loaded {} domain mappings", self.domain_mappings.len());
                },
                Err(e) => {
                    error!("Failed to parse configuration as UTF-8: {}", e);
                    return false;
                }
            }
        } else {
            warn!("No configuration provided, no redirects will be performed");
        }

        true
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            domain_mappings: self.domain_mappings.clone(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    domain_mappings: Rc<HashMap<String, String>>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        // Get the ":authority" header which contains the hostname
        if let Some(host) = self.get_http_request_header(":authority") {
            // Extract the domain part (remove port if present)
            let domain = host.split(':').next().unwrap_or(&host);

            // Check if this domain should be redirected
            if let Some(target_domain) = self.domain_mappings.get(domain) {
                // Get the path
                let path = self.get_http_request_header(":path").unwrap_or_default();

                // Get the scheme (http or https)
                let scheme = self.get_http_request_header(":scheme").unwrap_or("https");

                // Construct the new URL
                let new_url = format!("{}://{}{}", scheme, target_domain, path);

                // Send a 301 response with the new location
                self.send_http_response(
                    301,
                    vec![("Location", new_url.as_str())],
                    Some(format!("Redirecting to {}", new_url).as_bytes()),
                );

                return Action::Pause; // End stream and stop further processing
            }
        }

        Action::Continue
    }
}
// [END serviceextensions_plugin_redirect]