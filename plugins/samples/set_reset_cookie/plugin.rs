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
    fn on_configure(&mut self, plugin_configuration_size: usize) -> bool {
        // Handle empty configuration
        if plugin_configuration_size == 0 {
            log::warn!("Empty configuration provided, no cookies will be managed");
            return true; // Empty config is valid, just does nothing
        }

        let config_data = match self.get_plugin_configuration() {
            Some(data) => data,
            None => {
                log::error!("Failed to retrieve configuration data buffer");
                return false;
            }
        };

        let config_string = match String::from_utf8(config_data) {
            Ok(s) => s,
            Err(e) => {
                log::error!("Configuration is not valid UTF-8: {}", e);
                return false;
            }
        };

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

            if (cookie_config.operation() == CookieOperation::Set
                || cookie_config.operation() == CookieOperation::Overwrite)
                && cookie_config.value.is_empty()
            {
                log::warn!(
                    "Cookie '{}' has SET/OVERWRITE operation but empty value",
                    cookie_config.name
                );
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
            request_cookies: Vec::new(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct CookieManagerHttpContext {
    cookie_configs: Vec<CookieConfig>,
    // Ordered list of (name, value) pairs. A Vec (rather than a map) is used
    // because a Cookie header may legally contain several cookies with the
    // same name, and because it preserves the original order when the header
    // is rebuilt.
    request_cookies: Vec<(String, String)>,
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
    // Parse cookies from the Cookie header. Tolerates any amount of whitespace
    // around the ';' separators and keeps duplicate names.
    fn parse_request_cookies(&mut self) {
        self.request_cookies.clear();

        if let Some(cookie_header) = self.get_http_request_header("Cookie") {
            for pair in cookie_header.split(';') {
                let pair = pair.trim();
                if let Some(eq_pos) = pair.find('=') {
                    let name = pair[..eq_pos].trim();
                    let value = pair[eq_pos + 1..].trim();
                    if !name.is_empty() {
                        self.request_cookies
                            .push((name.to_string(), value.to_string()));
                    }
                }
            }
        }
    }

    // Process cookie deletions before CDN cache
    fn process_cookie_deletions(&mut self) {
        let mut names_to_delete: Vec<String> = Vec::new();

        for config in &self.cookie_configs {
            if config.operation() == CookieOperation::Delete
                && self.request_cookies.iter().any(|(n, _)| n == &config.name)
            {
                if !names_to_delete.contains(&config.name) {
                    names_to_delete.push(config.name.clone());
                }
                log::info!(
                    "Marking cookie for deletion before CDN cache: {}",
                    config.name
                );
            }
        }

        if names_to_delete.is_empty() {
            return;
        }

        // Remove every cookie whose name matches, however many there are
        self.request_cookies
            .retain(|(name, _)| !names_to_delete.contains(name));

        self.rebuild_cookie_header();
    }

    // Rebuild Cookie header from the remaining cookies (original order kept)
    fn rebuild_cookie_header(&self) {
        if self.request_cookies.is_empty() {
            self.set_http_request_header("Cookie", None);
        } else {
            let header = self
                .request_cookies
                .iter()
                .map(|(name, value)| format!("{}={}", name, value))
                .collect::<Vec<_>>()
                .join("; ");
            self.set_http_request_header("Cookie", Some(&header));
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

        // Add Max-Age for persistent cookies (session cookie otherwise)
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

        let log_type = if config.max_age > 0 {
            "persistent"
        } else {
            "session"
        };
        // Cookie values are intentionally not logged (may be sensitive)
        log::info!("Setting {} cookie: {}", log_type, config.name);
    }

    // Remove only the existing Set-Cookie headers for this cookie name,
    // leaving Set-Cookie headers for other cookies untouched.
    fn remove_existing_set_cookie(&self, name: &str) {
        let headers = self.get_http_response_headers();

        let is_set_cookie = |key: &str| key.eq_ignore_ascii_case("set-cookie");
        let matches_name = |value: &str| {
            value
                .split(';')
                .next()
                .and_then(|nv| nv.find('=').map(|eq| nv[..eq].trim() == name))
                .unwrap_or(false)
        };

        // Nothing to do if no Set-Cookie header targets this cookie
        if !headers
            .iter()
            .any(|(k, v)| is_set_cookie(k) && matches_name(v))
        {
            return;
        }

        // Header maps can't remove a single value, so clear all Set-Cookie
        // headers and re-add the ones that don't target this cookie.
        self.set_http_response_header("Set-Cookie", None);
        for (k, v) in headers.iter() {
            if is_set_cookie(k) && !matches_name(v) {
                self.add_http_response_header("Set-Cookie", v);
            }
        }
    }

    // Overwrite or remove existing Set-Cookie headers
    fn overwrite_cookie(&self, config: &CookieConfig) {
        // Remove existing Set-Cookie headers for this cookie only
        self.remove_existing_set_cookie(&config.name);

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

fn parse_text_proto(text: &str) -> Result<CookieManagerConfig, String> {
    protobuf::text_format::parse_from_str(text).map_err(|e| e.to_string())
}
// [END serviceextensions_plugin_set_reset_cookie]
