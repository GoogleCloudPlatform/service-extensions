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
use prost_reflect::{DescriptorPool, DynamicMessage, Value};
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

// FileDescriptorSet compiled from cookie_config.proto via Bazel genrule.
const DESCRIPTOR_BYTES: &[u8] = include_bytes!(env!("PROTO_DESCRIPTOR"));

// Cookie operation enum values from cookie_config.proto.
const OP_UNSPECIFIED: i32 = 0;
const OP_SET: i32 = 1;
const OP_DELETE: i32 = 2;
const OP_OVERWRITE: i32 = 3;

// Parsed cookie configuration.
struct CookieConfig {
    operation: i32,
    name: String,
    value: String,
    path: String,
    domain: String,
    max_age: i32,
    http_only: bool,
    secure: bool,
    same_site_strict: bool,
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

            // Parse text-format protobuf using prost-reflect.
            let pool = match DescriptorPool::decode(DESCRIPTOR_BYTES) {
                Ok(pool) => pool,
                Err(e) => {
                    error!("Failed to decode proto descriptor pool: {}", e);
                    return false;
                }
            };

            let msg_desc = match pool.get_message_by_name(
                "serviceextensions.cookie_manager.CookieManagerConfig",
            ) {
                Some(desc) => desc,
                None => {
                    error!("CookieManagerConfig message not found in proto descriptor");
                    return false;
                }
            };

            let config_msg = match DynamicMessage::parse_text_format(msg_desc, &config_str) {
                Ok(msg) => msg,
                Err(e) => {
                    error!(
                        "Failed to parse cookie manager configuration. \
                         Example: cookies {{ name: \"session\" value: \"abc\" operation: SET }}: {}",
                        e
                    );
                    return false;
                }
            };

            // Extract cookie configs from the parsed protobuf message.
            let mut configs = Vec::new();
            if let Some(cookies_cow) = config_msg.get_field_by_name("cookies") {
                if let Value::List(ref cookies) = *cookies_cow {
                    for cookie_value in cookies {
                        if let Value::Message(ref msg) = cookie_value {
                            let cookie = CookieConfig {
                                name: get_string(msg, "name"),
                                value: get_string(msg, "value"),
                                domain: get_string(msg, "domain"),
                                path: get_string(msg, "path"),
                                max_age: get_i32(msg, "max_age"),
                                secure: get_bool(msg, "secure"),
                                http_only: get_bool(msg, "http_only"),
                                same_site_strict: get_bool(msg, "same_site_strict"),
                                operation: get_enum(msg, "operation"),
                            };

                            if cookie.name.is_empty() {
                                error!("Cookie configuration missing required 'name' field");
                                continue;
                            }
                            configs.push(cookie);
                        }
                    }
                }
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

// Helper functions to extract typed values from a DynamicMessage.
fn get_string(msg: &DynamicMessage, field: &str) -> String {
    msg.get_field_by_name(field)
        .and_then(|cow| match cow.into_owned() {
            Value::String(s) => Some(s),
            _ => None,
        })
        .unwrap_or_default()
}

fn get_i32(msg: &DynamicMessage, field: &str) -> i32 {
    msg.get_field_by_name(field)
        .and_then(|cow| match *cow {
            Value::I32(v) => Some(v),
            _ => None,
        })
        .unwrap_or_default()
}

fn get_bool(msg: &DynamicMessage, field: &str) -> bool {
    msg.get_field_by_name(field)
        .and_then(|cow| match *cow {
            Value::Bool(v) => Some(v),
            _ => None,
        })
        .unwrap_or_default()
}

fn get_enum(msg: &DynamicMessage, field: &str) -> i32 {
    msg.get_field_by_name(field)
        .and_then(|cow| match *cow {
            Value::EnumNumber(v) => Some(v),
            _ => None,
        })
        .unwrap_or_default()
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
    fn parse_request_cookies(&self) -> Vec<(String, String)> {
        let mut cookies = Vec::new();
        if let Some(cookie_header) = self.get_http_request_header("Cookie") {
            if cookie_header.is_empty() {
                return cookies;
            }
            for pair in cookie_header.split("; ") {
                if let Some(eq_pos) = pair.find('=') {
                    cookies.push((pair[..eq_pos].to_string(), pair[eq_pos + 1..].to_string()));
                }
            }
        }
        cookies
    }

    fn process_cookie_deletions(&self, mut request_cookies: Vec<(String, String)>) {
        let mut modified = false;
        for config in self.cookie_configs.iter() {
            if config.operation != OP_DELETE {
                continue;
            }
            if let Some(pos) = request_cookies.iter().position(|(name, _)| name == &config.name) {
                request_cookies.remove(pos);
                modified = true;
                info!(
                    "Marking cookie for deletion before CDN cache: {}",
                    config.name
                );
            }
        }

        if modified {
            if request_cookies.is_empty() {
                self.set_http_request_header("Cookie", None);
            } else {
                let mut rebuilt = String::new();
                for (i, (name, value)) in request_cookies.iter().enumerate() {
                    if i > 0 {
                        rebuilt.push_str("; ");
                    }
                    rebuilt.push_str(name);
                    rebuilt.push('=');
                    rebuilt.push_str(value);
                }
                self.set_http_request_header("Cookie", Some(&rebuilt));
            }
        }
    }

    fn process_cookie_operations(&self) {
        for config in self.cookie_configs.iter() {
            match config.operation {
                OP_SET | OP_UNSPECIFIED => self.add_set_cookie_header(config),
                OP_OVERWRITE => self.overwrite_cookie(config),
                _ => {}
            }
        }
    }

    fn effective_path(config: &CookieConfig) -> &str {
        if config.path.is_empty() { "/" } else { &config.path }
    }

    fn build_set_cookie_value(&self, config: &CookieConfig) -> String {
        let mut val = format!("{}={}; Path={}", config.name, config.value, Self::effective_path(config));
        if !config.domain.is_empty() {
            val.push_str("; Domain=");
            val.push_str(&config.domain);
        }
        if config.max_age > 0 {
            val.push_str("; Max-Age=");
            val.push_str(&config.max_age.to_string());
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

    fn add_set_cookie_header(&self, config: &CookieConfig) {
        self.add_http_response_header("Set-Cookie", &self.build_set_cookie_value(config));
        let log_type = if config.max_age <= 0 { "session" } else { "persistent" };
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

        if !config.value.is_empty() {
            self.add_set_cookie_header(config);
        } else {
            let mut expire = format!("{}=; Path={}; Max-Age=0", config.name, Self::effective_path(config));
            if !config.domain.is_empty() {
                expire.push_str("; Domain=");
                expire.push_str(&config.domain);
            }
            self.add_http_response_header("Set-Cookie", &expire);
            info!("Removing Set-Cookie directive for: {}", config.name);
        }
    }
}
// [END serviceextensions_plugin_set_reset_cookie]
