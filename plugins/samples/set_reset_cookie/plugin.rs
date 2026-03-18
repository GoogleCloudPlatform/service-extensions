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
use log::*;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext {
            cookie_configs: Rc::new(Vec::new()),
        })
    });
}}

// Cookie operation types.
#[derive(Clone)]
enum CookieOp {
    Set,
    Delete,
    Overwrite,
}

// Parsed cookie configuration.
#[derive(Clone)]
struct CookieConfig {
    operation: CookieOp,
    name: String,
    value: String,
    path: String,
    domain: String,
    max_age: i64,
    http_only: bool,
    secure: bool,
    same_site_strict: bool,
}

impl CookieConfig {
    fn new() -> Self {
        CookieConfig {
            operation: CookieOp::Set,
            name: String::new(),
            value: String::new(),
            path: "/".to_string(),
            domain: String::new(),
            max_age: -1,
            http_only: false,
            secure: false,
            same_site_strict: false,
        }
    }
}

struct MyRootContext {
    cookie_configs: Rc<Vec<CookieConfig>>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        if let Some(config) = self.get_plugin_configuration() {
            let config_str = match String::from_utf8(config) {
                Ok(s) => s,
                Err(_) => {
                    error!("Failed to retrieve configuration data buffer");
                    return false;
                }
            };

            if config_str.is_empty() {
                warn!("Empty configuration provided, no cookies will be managed");
                return true;
            }

            let mut configs = Vec::new();

            // Parse pipe-delimited config lines:
            // OPERATION|name|value|path|domain|max_age|http_only|secure|same_site_strict
            for line in config_str.lines() {
                let line = line.trim();
                // Skip empty lines and comments.
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }

                let fields: Vec<&str> = line.split('|').collect();
                if fields.len() < 2 {
                    error!("Invalid config line: {}", line);
                    continue;
                }

                let mut cookie = CookieConfig::new();

                // Parse operation.
                match fields[0] {
                    "SET" => cookie.operation = CookieOp::Set,
                    "DELETE" => cookie.operation = CookieOp::Delete,
                    "OVERWRITE" => cookie.operation = CookieOp::Overwrite,
                    _ => {
                        error!("Unknown operation: {}", fields[0]);
                        continue;
                    }
                }

                cookie.name = fields[1].to_string();
                if cookie.name.is_empty() {
                    error!("Cookie name cannot be empty");
                    continue;
                }

                // Parse optional fields.
                if fields.len() > 2 {
                    cookie.value = fields[2].to_string();
                }
                if fields.len() > 3 && !fields[3].is_empty() {
                    cookie.path = fields[3].to_string();
                }
                if fields.len() > 4 {
                    cookie.domain = fields[4].to_string();
                }
                if fields.len() > 5 && !fields[5].is_empty() {
                    match fields[5].parse::<i64>() {
                        Ok(v) => cookie.max_age = v,
                        Err(_) => {
                            error!("Invalid max_age value: {}", fields[5]);
                            continue;
                        }
                    }
                }
                if fields.len() > 6 {
                    cookie.http_only = fields[6] == "true";
                }
                if fields.len() > 7 {
                    cookie.secure = fields[7] == "true";
                }
                if fields.len() > 8 {
                    cookie.same_site_strict = fields[8] == "true";
                }

                configs.push(cookie);
            }

            if configs.is_empty() {
                warn!("No valid cookie configurations found, no cookies will be managed");
                return true;
            }

            info!(
                "Successfully loaded {} cookie configuration(s)",
                configs.len()
            );
            self.cookie_configs = Rc::new(configs);
        } else {
            warn!("Empty configuration provided, no cookies will be managed");
        }

        true
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            cookie_configs: self.cookie_configs.clone(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    cookie_configs: Rc<Vec<CookieConfig>>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        let request_cookies = self.parse_request_cookies();
        self.process_cookie_deletions(request_cookies);
        Action::Continue
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        self.process_cookie_operations();
        Action::Continue
    }
}

impl MyHttpContext {
    // Parse cookies from the Cookie request header.
    // Returns a vector of (name, value) pairs to preserve original order.
    fn parse_request_cookies(&self) -> Vec<(String, String)> {
        let mut cookies = Vec::new();
        if let Some(cookie_header) = self.get_http_request_header("Cookie") {
            if cookie_header.is_empty() {
                return cookies;
            }
            for pair in cookie_header.split("; ") {
                if let Some(eq_pos) = pair.find('=') {
                    let name = &pair[..eq_pos];
                    let value = &pair[eq_pos + 1..];
                    cookies.push((name.to_string(), value.to_string()));
                }
            }
        }
        cookies
    }

    // Remove cookies marked for DELETE from the request Cookie header.
    fn process_cookie_deletions(&self, mut request_cookies: Vec<(String, String)>) {
        let mut modified = false;
        for config in self.cookie_configs.iter() {
            if let CookieOp::Delete = config.operation {
                if let Some(pos) = request_cookies.iter().position(|(name, _)| name == &config.name)
                {
                    request_cookies.remove(pos);
                    modified = true;
                    info!(
                        "Marking cookie for deletion before CDN cache: {}",
                        config.name
                    );
                }
            }
        }

        if modified {
            if request_cookies.is_empty() {
                self.set_http_request_header("Cookie", None);
            } else {
                let rebuilt: Vec<String> = request_cookies
                    .iter()
                    .map(|(name, value)| format!("{}={}", name, value))
                    .collect();
                self.set_http_request_header("Cookie", Some(&rebuilt.join("; ")));
            }
        }
    }

    // Process SET and OVERWRITE operations on response headers.
    fn process_cookie_operations(&self) {
        for config in self.cookie_configs.iter() {
            match config.operation {
                CookieOp::Set => {
                    self.add_set_cookie_header(config);
                }
                CookieOp::Overwrite => {
                    self.overwrite_cookie(config);
                }
                CookieOp::Delete => {} // Handled in request phase.
            }
        }
    }

    // Build a Set-Cookie header value string from config attributes.
    fn build_set_cookie_value(&self, config: &CookieConfig) -> String {
        let mut val = format!("{}={}", config.name, config.value);
        val.push_str(&format!("; Path={}", config.path));
        if !config.domain.is_empty() {
            val.push_str(&format!("; Domain={}", config.domain));
        }
        if config.max_age > 0 {
            val.push_str(&format!("; Max-Age={}", config.max_age));
        }
        if config.http_only {
            val.push_str("; HttpOnly");
        }
        if config.secure {
            val.push_str("; Secure");
        }
        if config.same_site_strict {
            val.push_str("; SameSite=Strict");
        }
        val
    }

    // Add a new Set-Cookie response header.
    fn add_set_cookie_header(&self, config: &CookieConfig) {
        self.add_http_response_header("Set-Cookie", &self.build_set_cookie_value(config));
        let log_type = if config.max_age == -1 {
            "session"
        } else {
            "persistent"
        };
        info!("Setting {} cookie: {}", log_type, config.name);
    }

    // Overwrite an existing Set-Cookie header for the target cookie name,
    // preserving other Set-Cookie headers.
    // Note: The proxy-wasm host combines multiple Set-Cookie headers into a
    // single comma-separated value, so we split and reconstruct. This means
    // origin cookies using the Expires attribute (which contains a comma in its
    // date format) will be corrupted. Use Max-Age instead of Expires.
    fn overwrite_cookie(&self, config: &CookieConfig) {
        let existing = self.get_http_response_header("Set-Cookie");
        self.set_http_response_header("Set-Cookie", None);

        // Preserve non-matching Set-Cookie values from the combined header.
        if let Some(existing_value) = existing {
            if !existing_value.is_empty() {
                let prefix = format!("{}=", config.name);
                for cookie in existing_value.split(", ") {
                    if !cookie.starts_with(&prefix) {
                        self.add_http_response_header("Set-Cookie", cookie);
                    }
                }
            }
        }

        // Set the new value or expire the cookie.
        if !config.value.is_empty() {
            self.add_set_cookie_header(config);
        } else {
            let mut expire = format!("{}=; Path={}; Max-Age=0", config.name, config.path);
            if !config.domain.is_empty() {
                expire.push_str(&format!("; Domain={}", config.domain));
            }
            self.add_http_response_header("Set-Cookie", &expire);
            info!("Removing Set-Cookie directive for: {}", config.name);
        }
    }
}
// [END serviceextensions_plugin_set_reset_cookie]
