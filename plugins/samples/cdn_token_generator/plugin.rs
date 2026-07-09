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

// [START serviceextensions_plugin_cdn_token_generator_rust]
//
// This plugin signs URLs embedded in response bodies (e.g., HLS/DASH manifests)
// with HMAC-SHA256 tokens for Google Cloud Media CDN authentication.
//
// Use case: A video streaming service returns a manifest file (.m3u8 or .mpd)
// from the origin containing segment URLs. This plugin intercepts the response,
// finds all HTTP/HTTPS URLs, and replaces them with signed URLs that include
// authentication tokens. This allows Media CDN to verify that requests for
// video segments come from authorized clients.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use hmac::{Hmac, Mac};
use log::{error, info, warn};
use proxy_wasm::traits::{Context, HttpContext, RootContext};
use proxy_wasm::types::{Action, ContextType, LogLevel};
use regex::Regex;
use sha2::Sha256;
use std::time::UNIX_EPOCH;

type HmacSha256 = Hmac<Sha256>;

const MAX_KEY_HEX_LENGTH: usize = 256;
const MIN_KEY_HEX_LENGTH: usize = 32;
const MAX_EXPIRY_SECONDS: i32 = 86400; // 24 hours
const MIN_EXPIRY_SECONDS: i32 = 60; // 1 minute
const DEFAULT_EXPIRY_SECONDS: i32 = 3600;
const MAX_BODY_SIZE: usize = 1024 * 1024; // 1MB

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(CdnTokenRoot {
            decoded_key: Vec::new(),
            key_name: String::new(),
            expiry_seconds: DEFAULT_EXPIRY_SECONDS,
            url_pattern: Regex::new(r"(https?://[^\s\x22'<>]+)").unwrap(),
        })
    });
}}

struct CdnTokenRoot {
    decoded_key: Vec<u8>,
    key_name: String,
    expiry_seconds: i32,
    url_pattern: Regex,
}

impl Context for CdnTokenRoot {}

impl RootContext for CdnTokenRoot {
    // ESSENCIAL: Diz ao Envoy que este Root cria contextos HTTP
    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }

    fn on_configure(&mut self, _plugin_configuration_size: usize) -> bool {
        let config_bytes = match self.get_plugin_configuration() {
            Some(c) if !c.is_empty() => c,
            _ => {
                error!("Configuration is required");
                return false;
            }
        };

        let config_str = match String::from_utf8(config_bytes) {
            Ok(s) => s,
            Err(_) => {
                error!("Failed to parse configuration as UTF-8");
                return false;
            }
        };

        if !self.parse_config(&config_str) {
            return false;
        }

        info!(
            "CDN Token Generator configured: keyName={}, expirySeconds={}",
            self.key_name, self.expiry_seconds
        );

        true
    }

    fn create_http_context(&self, context_id: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(CdnTokenHttp {
            decoded_key: self.decoded_key.clone(),
            key_name: self.key_name.clone(),
            expiry_seconds: self.expiry_seconds,
            url_pattern: self.url_pattern.clone(),
            _context_id: context_id,
        }))
    }
}

impl CdnTokenRoot {
    fn parse_config(&mut self, config_str: &str) -> bool {
        let mut private_key_hex = String::new();
        self.key_name.clear();
        self.expiry_seconds = DEFAULT_EXPIRY_SECONDS;

        // Simple line parser for `.textpb` without heavy Protobuf dependencies
        for line in config_str.lines() {
            let line = line.trim();
            if line.starts_with("private_key_hex:") {
                private_key_hex = Self::extract_quoted_value(line);
            } else if line.starts_with("key_name:") {
                self.key_name = Self::extract_quoted_value(line);
            } else if line.starts_with("expiry_seconds:") {
                if let Some(val) = Self::extract_int_value(line) {
                    self.expiry_seconds = val;
                }
            }
        }

        if private_key_hex.is_empty() {
            error!("private_key_hex is required in configuration");
            return false;
        }
        if self.key_name.is_empty() {
            error!("key_name is required in configuration");
            return false;
        }
        if private_key_hex.len() < MIN_KEY_HEX_LENGTH || private_key_hex.len() > MAX_KEY_HEX_LENGTH {
            error!(
                "private_key_hex length must be between {} and {}",
                MIN_KEY_HEX_LENGTH, MAX_KEY_HEX_LENGTH
            );
            return false;
        }
        if self.expiry_seconds < MIN_EXPIRY_SECONDS || self.expiry_seconds > MAX_EXPIRY_SECONDS {
            error!(
                "expiry_seconds must be between {} and {}",
                MIN_EXPIRY_SECONDS, MAX_EXPIRY_SECONDS
            );
            return false;
        }

        match hex::decode(&private_key_hex) {
            Ok(key) => self.decoded_key = key,
            Err(_) => {
                error!("Failed to decode private key from hex");
                return false;
            }
        }

        true
    }

    fn extract_quoted_value(line: &str) -> String {
        let parts: Vec<&str> = line.splitn(2, ':').collect();
        if parts.len() == 2 {
            parts[1].trim().trim_matches('"').to_string()
        } else {
            String::new()
        }
    }

    fn extract_int_value(line: &str) -> Option<i32> {
        let parts: Vec<&str> = line.splitn(2, ':').collect();
        if parts.len() == 2 {
            parts[1].trim().parse::<i32>().ok()
        } else {
            None
        }
    }
}

struct CdnTokenHttp {
    decoded_key: Vec<u8>,
    key_name: String,
    expiry_seconds: i32,
    url_pattern: Regex,
    _context_id: u32,
}

impl Context for CdnTokenHttp {}

impl HttpContext for CdnTokenHttp {
    fn on_http_response_body(&mut self, body_size: usize, end_of_stream: bool) -> Action {
        if !end_of_stream {
            return Action::Pause;
        }

        if body_size > MAX_BODY_SIZE {
            warn!(
                "Response body too large ({} bytes), skipping URL signing",
                body_size
            );
            return Action::Continue;
        }

        let body_bytes = match self.get_http_response_body(0, body_size) {
            Some(b) => b,
            None => {
                error!("Failed to read response body");
                return Action::Continue;
            }
        };

        let body_string = match String::from_utf8(body_bytes) {
            Ok(s) => s,
            Err(_) => {
                // Ignore non-utf8 bodies safely
                return Action::Continue;
            }
        };

        if body_string.is_empty() {
            return Action::Continue;
        }

        let mut replacements = Vec::new();

        for mat in self.url_pattern.find_iter(&body_string) {
            let url = mat.as_str();
            if let Some(signed_url) = self.generate_signed_url(url) {
                replacements.push((mat.start(), mat.end(), signed_url));
            }
        }

        if replacements.is_empty() {
            return Action::Continue;
        }

        let mut modified_body = String::with_capacity(body_string.len() + replacements.len() * 100);
        let mut last_end = 0;

        for (start, end, signed_url) in replacements.iter() {
            modified_body.push_str(&body_string[last_end..*start]);
            modified_body.push_str(signed_url);
            last_end = *end;
        }
        modified_body.push_str(&body_string[last_end..]);

        info!("Replaced {} URLs with signed URLs", replacements.len());
        self.set_http_response_body(0, body_size, modified_body.as_bytes());

        Action::Continue
    }
}

impl CdnTokenHttp {
    fn generate_signed_url(&self, target_url: &str) -> Option<String> {
        let url_prefix_b64 = URL_SAFE_NO_PAD.encode(target_url);

        // Utilize the get_current_time trait implementation securely
        let now = self.get_current_time().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
        let expires_at = now + (self.expiry_seconds as u64);

        let string_to_sign = format!(
            "URLPrefix={}~Expires={}~KeyName={}",
            url_prefix_b64, expires_at, self.key_name
        );

        let mut mac = HmacSha256::new_from_slice(&self.decoded_key).ok()?;
        mac.update(string_to_sign.as_bytes());
        let hmac_result = mac.finalize().into_bytes();
        let hmac_hex = hex::encode(hmac_result);

        let separator = if target_url.contains('?') { "&" } else { "?" };

        Some(format!(
            "{}{}Edge-Cache-Token={}~hmac={}",
            target_url, separator, string_to_sign, hmac_hex
        ))
    }
}
// [END serviceextensions_plugin_cdn_token_generator_rust]
