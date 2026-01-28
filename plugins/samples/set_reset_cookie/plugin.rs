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

// [START serviceextensions_plugin_set_reset_cookie]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::collections::HashMap;

// Include the generated protobuf code
include!(concat!(env!("OUT_DIR"), "/cookie_config.rs"));

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(CookieManagerRootContext::default())
    });
}}

#[derive(Default)]
struct CookieManagerRootContext {
    cookie_configs: Vec<CookieConfig>,
}

impl Context for CookieManagerRootContext {}

impl RootContext for CookieManagerRootContext {
    fn on_configure(&mut self, _plugin_configuration_size: usize) -> bool {
        // Handle empty configuration
        if _plugin_configuration_size == 0 {
            log::warn!("Empty configuration provided, no cookies will be managed");
            self.cookie_configs.clear();
            return true; // Empty config is valid, just does nothing
        }

        let config_data = match self.get_plugin_configuration() {
            Some(data) => data,
            None => {
                log::error!("Failed to retrieve configuration data buffer");
                return false;
            }
        };

        let config_string = match String::from_utf8(config_data.clone()) {
            Ok(s) => s,
            Err(e) => {
                log::error!("Configuration is not valid UTF-8: {}", e);
                return false;
            }
        };

        // Parse the protobuf configuration using prost-reflect or manual parsing
        // Note: For text protobuf parsing, you might need to use a text format parser
        // This is a simplified version - you may need to adjust based on your protobuf setup
        let config: CookieManagerConfig = match parse_text_proto(&config_string) {
            Ok(c) => c,
            Err(e) => {
                log::error!(
                    "Failed to parse cookie manager configuration as text protobuf. \
                    Please ensure configuration follows the text protobuf format. \
                    Example: cookies {{ name: \"session\" value: \"abc\" }}. Error: {}",
                    e
                );
                return false;
            }
        };

        // Validate parsed configuration
        if config.cookies.is_empty() {
            log::warn!("Configuration parsed successfully but contains no cookie definitions");
            self.cookie_configs.clear();
            return true;
        }

        // Store the parsed cookie configurations with validation
        self.cookie_configs.clear();
        let mut valid_cookies = 0;

        for cookie_config in config.cookies {
            // Validate required fields based on operation type
            if cookie_config.name.is_empty() {
                log::error!("Cookie configuration missing required 'name' field, skipping");
                continue;
            }

            if cookie_config.operation() == CookieOperation::Set
                || cookie_config.operation() == CookieOperation::Overwrite
            {
                if cookie_config.value.is_empty() {
                    log::warn!(
                        "Cookie '{}' has SET/OVERWRITE operation but empty value",
                        cookie_config.name
                    );
                }
            }

            log::debug!(
                "Configured cookie: name={}, operation={:?}",
                cookie_config.name,
                cookie_config.operation()
            );

            self.cookie_configs.push(cookie_config);
            valid_cookies += 1;
        }

        if valid_cookies == 0 {
            log::error!("No valid cookie configurations found after validation");
            return false;
        }

        log::info!("Successfully loaded {} cookie configuration(s)", valid_cookies);
        true
    }

    fn create_http_context(&self, _context_id: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(CookieManagerHttpContext {
            cookie_configs: self.cookie_configs.clone(),
            request_cookies: HashMap::new(),
            cookies_to_delete: Vec::new(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct CookieManagerHttpContext {
    cookie_configs: Vec<CookieConfig>,
    request_cookies: HashMap<String, String>,
    cookies_to_delete: Vec<String>,
}

impl Context for CookieManagerHttpContext {}

impl HttpContext for CookieManagerHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        // Parse existing cookies from request
        self.parse_request_cookies();

        // Process DELETE operations before CDN cache
        self.process_cookie_deletions();

        Action::Continue
    }

    fn on_http_response_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        // Process SET and OVERWRITE operations
        self.process_cookie_operations();

        Action::Continue
    }
}

impl CookieManagerHttpContext {
    // Parse cookies from the Cookie header
    fn parse_request_cookies(&mut self) {
        if let Some(cookie_header) = self.get_http_request_header("Cookie") {
            for cookie_pair in cookie_header.split("; ") {
                let parts: Vec<&str> = cookie_pair.splitn(2, '=').collect();
                if parts.len() == 2 {
                    self.request_cookies
                        .insert(parts[0].to_string(), parts[1].to_string());
                }
            }
        }
    }

    // Process cookie deletions before CDN cache
    fn process_cookie_deletions(&mut self) {
        for config in &self.cookie_configs {
            if config.operation() == CookieOperation::Delete {
                if self.request_cookies.contains_key(&config.name) {
                    self.cookies_to_delete.push(config.name.clone());
                    log::info!(
                        "Marking cookie for deletion before CDN cache: {}",
                        config.name
                    );
                }
            }
        }

        // Remove deleted cookies from request
        if !self.cookies_to_delete.is_empty() {
            self.rebuild_cookie_header();
        }
    }

    // Rebuild Cookie header without deleted cookies
    fn rebuild_cookie_header(&self) {
        let mut remaining_cookies = Vec::new();

        for (name, value) in &self.request_cookies {
            if !self.cookies_to_delete.contains(name) {
                remaining_cookies.push(format!("{}={}", name, value));
            }
        }

        if remaining_cookies.is_empty() {
            self.set_http_request_header("Cookie", None);
        } else {
            self.set_http_request_header("Cookie", Some(&remaining_cookies.join("; ")));
        }
    }

    // Process SET and OVERWRITE operations
    fn process_cookie_operations(&self) {
        for config in &self.cookie_configs {
            match config.operation() {
                CookieOperation::Set => self.set_cookie(config),
                CookieOperation::Overwrite => self.overwrite_cookie(config),
                _ => {}
            }
        }
    }

    // Set or reset a cookie
    fn set_cookie(&self, config: &CookieConfig) {
        let mut cookie_value = format!("{}={}", config.name, config.value);

        // Add Path attribute
        cookie_value.push_str(&format!("; Path={}", config.path));

        // Add Domain attribute if specified
        if !config.domain.is_empty() {
            cookie_value.push_str(&format!("; Domain={}", config.domain));
        }

        // Add Max-Age for persistent cookies (session if -1)
        if config.max_age > 0 {
            cookie_value.push_str(&format!("; Max-Age={}", config.max_age));
        }

        // Add security attributes
        if config.http_only {
            cookie_value.push_str("; HttpOnly");
        }

        if config.secure {
            cookie_value.push_str("; Secure");
        }

        if config.same_site_strict {
            cookie_value.push_str("; SameSite=Strict");
        }

        self.add_http_response_header("Set-Cookie", &cookie_value);

        let log_type = if config.max_age == -1 {
            "session"
        } else {
            "persistent"
        };
        log::info!(
            "Setting {} cookie: {}={}",
            log_type,
            config.name,
            config.value
        );
    }

    // Overwrite or remove existing Set-Cookie headers
    fn overwrite_cookie(&self, config: &CookieConfig) {
        // Remove all existing Set-Cookie headers for this cookie
        self.set_http_response_header("Set-Cookie", None);

        // If value is not empty, set the new cookie
        if !config.value.is_empty() {
            self.set_cookie(config);
            log::info!("Overwriting existing cookie: {}", config.name);
        } else {
            // Complete removal - set expired cookie
            let mut expire_cookie = format!("{}=; Path={}; Max-Age=0", config.name, config.path);

            if !config.domain.is_empty() {
                expire_cookie.push_str(&format!("; Domain={}", config.domain));
            }

            self.add_http_response_header("Set-Cookie", &expire_cookie);
            log::info!("Removing Set-Cookie directive for: {}", config.name);
        }
    }
}

// Helper function to parse text protobuf format
// Note: This is a placeholder - you'll need to implement or use a library for text proto parsing
fn parse_text_proto(text: &str) -> Result<CookieManagerConfig, String> {
    // This is a simplified parser. In production, you should use a proper text format parser
    // or consider using JSON/binary protobuf instead
    
    // For now, returning an error to indicate this needs proper implementation
    Err("Text protobuf parsing not fully implemented. Please use binary protobuf or implement a text parser.".to_string())
    
    // You could use prost-reflect or implement a custom parser here
    // Example with hypothetical parser:
    // prost_reflect::text_format::parse::<CookieManagerConfig>(text)
    //     .map_err(|e| e.to_string())
}
// [END serviceextensions_plugin_set_reset_cookie]