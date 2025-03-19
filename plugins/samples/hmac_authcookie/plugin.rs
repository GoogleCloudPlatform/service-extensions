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

// [START serviceextensions_plugin_hmac_authcookie]
use base64::Engine as _;
const BASE64_ENGINE: base64::engine::GeneralPurpose = base64::engine::general_purpose::URL_SAFE_NO_PAD;
use hmac::{Hmac, Mac};
use proxy_wasm::{
    traits::{Context, HttpContext, RootContext},
    types::{Action, LogLevel},
};
use regex::Regex;
use sha2::Sha256;
use std::time::SystemTime;

// Replace with your desired secret key
const SECRET_KEY: &[u8] = b"your_secret_key";

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Info);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext {
            // Regex for matching IPv4 addresses like 127.0.0.1
            ip_regex: Regex::new(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$").unwrap()
        })
    });
}}

struct MyRootContext {
    ip_regex: Regex,
}

impl RootContext for MyRootContext {
    fn get_type(&self) -> Option<proxy_wasm::types::ContextType> {
        Some(proxy_wasm::types::ContextType::HttpContext)
    }

    // Creates HTTP context for each request
    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            ip_regex: self.ip_regex.clone(),
        }))
    }
}

impl Context for MyRootContext {}

struct MyHttpContext {
    ip_regex: Regex,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // 1. Get client IP from X-Forwarded-For header
        let client_ip = match self.get_client_ip() {
            Some(ip) => ip,
            None => {
                self.respond_with_error(403, "Access forbidden - missing client IP.");
                return Action::Pause;
            }
        };

        // 2. Get Authorization cookie value
        let token = match self.get_auth_cookie() {
            Some(token) => token,
            None => {
                self.respond_with_error(403, "Access forbidden - missing HMAC cookie.");
                return Action::Pause;
            }
        };

        // 3. Split cookie into payload and signature
        let (payload, signature) = match self.parse_auth_cookie(&token) {
            Some((p, s)) => (p, s),
            None => {
                self.respond_with_error(403, "Access forbidden - invalid HMAC cookie.");
                return Action::Pause;
            }
        };

        // 4. Verify HMAC signature
        if !self.verify_hmac(&payload, &signature) {
            self.respond_with_error(403, "Access forbidden - invalid HMAC hash.");
            return Action::Pause;
        }

        // 5. Validate IP match and expiration time
        let (ip, exp) = match self.parse_payload(&payload) {
            Some((i, e)) => (i, e),
            None => {
                self.respond_with_error(403, "Access forbidden - invalid payload format.");
                return Action::Pause;
            }
        };

        if ip != client_ip {
            self.respond_with_error(403, "Access forbidden - invalid client IP.");
            return Action::Pause;
        }

        if !self.validate_expiration(&exp) {
            self.respond_with_error(403, "Access forbidden - hash expired.");
            return Action::Pause;
        }

        Action::Continue
    }
}

impl MyHttpContext {
    // Sends HTTP response with status and message
    fn respond_with_error(&self, status: u32, message: &str) {
        proxy_wasm::hostcalls::log(LogLevel::Info, message).unwrap();
        self.send_http_response(
            status,
            vec![("Content-Type", "text/plain")],
            Some(format!("{}\n", message).as_bytes()),
        );
    }

    // Tries to get client IP from X-Forwarded-For header
    fn get_client_ip(&self) -> Option<String> {
        self.get_http_request_header("X-Forwarded-For")
            .unwrap_or_default()
            .split(',')
            .find_map(|ip| {
                let ip = ip.trim();
                self.ip_regex.is_match(ip).then(|| ip.to_string())
            })
    }

    // Extracts Authorization cookie value
    fn get_auth_cookie(&self) -> Option<String> {
        self.get_http_request_header("Cookie")
            .unwrap_or_default()
            .split("; ")
            .find_map(|cookie| {
                let mut parts = cookie.splitn(2, '=');
                if let (Some("Authorization"), Some(value)) = (parts.next(), parts.next()) {
                    Some(value.to_string())
                } else {
                    None
                }
            })
    }

    // Parses cookie into decoded payload and signature bytes
    fn parse_auth_cookie(&self, token: &str) -> Option<(String, Vec<u8>)> {
        let mut parts = token.splitn(2, '.');
        let (payload_b64, signature_b64) = (parts.next()?, parts.next()?);
        
        // Decode payload (Base64 → String)
        let payload = BASE64_ENGINE.decode(payload_b64).ok()?;
        let payload_str = String::from_utf8(payload).ok()?;
        
        // Decode signature (Base64 → Bytes)
        let signature = BASE64_ENGINE.decode(signature_b64).ok()?;
        
        Some((payload_str, signature))
    }

    // Verifies HMAC-SHA256 signature
    fn verify_hmac(&self, payload: &str, signature: &[u8]) -> bool {
        let mut mac = Hmac::<Sha256>::new_from_slice(SECRET_KEY).unwrap();
        mac.update(payload.as_bytes());
        let hmac_result = mac.finalize().into_bytes();
        
        // Convert HMAC to hexadecimal
        let hmac_hex = hex::encode(hmac_result);
        
        // Compare with decoded signature (hexadecimal string)
        hmac_hex.as_bytes() == signature
    }

    // Splits payload into IP and expiration components
    fn parse_payload(&self, payload: &str) -> Option<(String, String)> {
        let mut parts = payload.splitn(2, ',');
        match (parts.next(), parts.next()) {
            (Some(ip), Some(exp)) => Some((ip.to_string(), exp.to_string())),
            _ => None,
        }
    }

    // Checks if current time is before expiration timestamp
    fn validate_expiration(&self, exp: &str) -> bool {
        let current_time = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_nanos() as i64;
        
        exp.parse::<i64>()
            .map(|exp_time| current_time <= exp_time)
            .unwrap_or(false)
    }
}
// [END serviceextensions_plugin_hmac_authcookie]