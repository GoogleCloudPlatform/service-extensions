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

// [START serviceextensions_plugin_jwt_generator]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};
use hmac::{Hmac, Mac};
use sha2::Sha256;
use base64::{Engine as _, engine::general_purpose};

type HmacSha256 = Hmac<Sha256>;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Info);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(JwtRootContext {
            config: None,
        })
    });
}}

// Configuration structures
#[derive(Debug, Deserialize, Clone)]
struct PluginConfig {
    secret_key: String,
    default_expiration_minutes: Option<i64>,
    data: HashMap<String, UserEntitlements>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct UserEntitlements {
    plan: String,
    permissions: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    roles: Option<Vec<String>>,
}

// JWT structures
#[derive(Debug, Serialize)]
struct JwtHeader {
    alg: String,
    typ: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct JwtPayload {
    sub: String,
    exp: i64,
    nbf: i64,
    iat: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    plan: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    permissions: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    roles: Option<Vec<String>>,
}

// Response structures
#[derive(Debug, Serialize)]
struct TokenResponse {
    token: String,
    expires_in: i64,
    token_type: String,
}

#[derive(Debug, Serialize)]
struct VerifyResponse {
    valid: bool,
    message: String,
}

// Root context for plugin configuration
struct JwtRootContext {
    config: Option<PluginConfig>,
}

impl Context for JwtRootContext {}

impl RootContext for JwtRootContext {
    fn on_configure(&mut self, _plugin_configuration_size: usize) -> bool {
        if let Some(config_bytes) = self.get_plugin_configuration() {
            match serde_json::from_slice::<PluginConfig>(&config_bytes) {
                Ok(config) => {
                    proxy_wasm::hostcalls::log(
                        LogLevel::Info,
                        &format!("JWT Plugin configured with {} KV store entries", config.data.len())
                    ).unwrap();
                    self.config = Some(config);
                    true
                }
                Err(e) => {
                    proxy_wasm::hostcalls::log(
                        LogLevel::Error,
                        &format!("Failed to parse configuration: {}", e)
                    ).unwrap();
                    false
                }
            }
        } else {
            proxy_wasm::hostcalls::log(
                LogLevel::Warn,
                "No configuration provided, using defaults"
            ).unwrap();
            self.config = Some(PluginConfig {
                secret_key: "default_secret_key_change_me".to_string(),
                default_expiration_minutes: Some(60),
                data: HashMap::new(),
            });
            true
        }
    }

    fn create_http_context(&self, _context_id: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(JwtHttpContext {
            config: self.config.clone(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

// HTTP context for request handling
struct JwtHttpContext {
    config: Option<PluginConfig>,
}

impl Context for JwtHttpContext {}

impl HttpContext for JwtHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        let path = match self.get_http_request_header(":path") {
            Some(p) => p,
            None => {
                proxy_wasm::hostcalls::log(LogLevel::Error, "Failed to get :path header").unwrap();
                return Action::Continue;
            }
        };

        let method = self.get_http_request_header(":method").unwrap_or_default();

        // Route to appropriate handler
        match (path.as_str(), method.as_str()) {
            ("/generate-token", "POST") => self.handle_generate_token(),
            ("/verify-token", "GET") => self.handle_verify_token(),
            _ => self.handle_protected_endpoint(),
        }
    }
}

impl JwtHttpContext {
    fn handle_generate_token(&mut self) -> Action {
        // Get user_id from header
        let user_id = match self.get_http_request_header("x-user-id") {
            Some(id) if !id.is_empty() => id,
            _ => {
                self.send_json_response(
                    400,
                    &serde_json::json!({"error": "Missing x-user-id header"})
                );
                return Action::Pause;
            }
        };

        // Get optional expiration override
        let config = self.config.as_ref().unwrap();
        let default_exp = config.default_expiration_minutes.unwrap_or(60);
        let expiration_minutes = self
            .get_http_request_header("x-expiration-minutes")
            .and_then(|exp| exp.parse::<i64>().ok())
            .unwrap_or(default_exp);

        // Generate JWT
        match self.generate_jwt(&user_id, expiration_minutes) {
            Ok(token) => {
                let response = TokenResponse {
                    token,
                    expires_in: expiration_minutes * 60,
                    token_type: "Bearer".to_string(),
                };
                self.send_json_response(200, &response);
            }
            Err(e) => {
                proxy_wasm::hostcalls::log(
                    LogLevel::Error,
                    &format!("Failed to generate JWT: {}", e)
                ).unwrap();
                self.send_json_response(
                    500,
                    &serde_json::json!({"error": "Failed to generate token"})
                );
            }
        }

        Action::Pause
    }

    fn handle_verify_token(&mut self) -> Action {
        // Get Authorization header
        let auth_header = match self.get_http_request_header("authorization") {
            Some(h) if !h.is_empty() => h,
            _ => {
                self.send_json_response(
                    401,
                    &VerifyResponse {
                        valid: false,
                        message: "Missing Authorization header".to_string(),
                    }
                );
                return Action::Pause;
            }
        };

        // Extract Bearer token
        if !auth_header.starts_with("Bearer ") {
            self.send_json_response(
                401,
                &VerifyResponse {
                    valid: false,
                    message: "Invalid Authorization format".to_string(),
                }
            );
            return Action::Pause;
        }

        let token = &auth_header[7..];

        // Verify token
        match self.verify_jwt(token) {
            Ok(_) => {
                self.send_json_response(
                    200,
                    &VerifyResponse {
                        valid: true,
                        message: "Token is valid".to_string(),
                    }
                );
            }
            Err(e) => {
                self.send_json_response(
                    401,
                    &VerifyResponse {
                        valid: false,
                        message: e,
                    }
                );
            }
        }

        Action::Pause
    }

    fn handle_protected_endpoint(&mut self) -> Action {
        // Get Authorization header
        let auth_header = match self.get_http_request_header("authorization") {
            Some(h) if !h.is_empty() => h,
            None => return Action::Continue, // No token, continue to upstream
        };

        // Check if it's a Bearer token
        if !auth_header.starts_with("Bearer ") {
            return Action::Continue;
        }

        let token = &auth_header[7..];

        // Verify token
        if let Err(e) = self.verify_jwt(token) {
            self.send_http_response(
                401,
                vec![("Content-Type", "text/plain")],
                Some(format!("Unauthorized: {}", e).as_bytes())
            );
            return Action::Pause;
        }

        // Extract payload and add headers for downstream services
        if let Ok(payload) = self.decode_payload(token) {
            self.add_http_request_header("x-jwt-user", &payload.sub);
            if let Some(plan) = payload.plan {
                self.add_http_request_header("x-jwt-plan", &plan);
            }
        }

        Action::Continue
    }

    fn generate_jwt(&self, user_id: &str, expiration_minutes: i64) -> Result<String, String> {
        let config = self.config.as_ref().ok_or("No configuration available")?;
        
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|e| format!("System time error: {}", e))?
            .as_secs() as i64;

        let exp = now + (expiration_minutes * 60);

        // Create JWT header
        let header = JwtHeader {
            alg: "HS256".to_string(),
            typ: "JWT".to_string(),
        };

        // Get user entitlements from KV store
        let entitlements = self.get_user_entitlements(user_id);

        // Create JWT payload
        let payload = JwtPayload {
            sub: user_id.to_string(),
            exp,
            nbf: now,
            iat: now,
            plan: Some(entitlements.plan),
            permissions: Some(entitlements.permissions),
            roles: entitlements.roles,
        };

        // Encode header
        let header_json = serde_json::to_string(&header)
            .map_err(|e| format!("Failed to serialize header: {}", e))?;
        let header_encoded = base64_url_encode(header_json.as_bytes());

        // Encode payload
        let payload_json = serde_json::to_string(&payload)
            .map_err(|e| format!("Failed to serialize payload: {}", e))?;
        let payload_encoded = base64_url_encode(payload_json.as_bytes());

        // Create signature
        let signing_input = format!("{}.{}", header_encoded, payload_encoded);
        let signature = self.hmac_sha256(&config.secret_key, &signing_input)?;
        let signature_encoded = base64_url_encode(&signature);

        // Assemble final JWT
        Ok(format!("{}.{}", signing_input, signature_encoded))
    }

    fn verify_jwt(&self, token: &str) -> Result<(), String> {
        let config = self.config.as_ref().ok_or("No configuration available")?;

        // Split token into parts
        let parts: Vec<&str> = token.split('.').collect();
        if parts.len() != 3 {
            return Err("Invalid token format".to_string());
        }

        // Verify signature
        let signing_input = format!("{}.{}", parts[0], parts[1]);
        let expected_signature = self.hmac_sha256(&config.secret_key, &signing_input)?;
        let expected_signature_encoded = base64_url_encode(&expected_signature);

        if parts[2] != expected_signature_encoded {
            return Err("Invalid signature".to_string());
        }

        // Decode and verify payload
        let payload_bytes = base64_url_decode(parts[1])
            .map_err(|e| format!("Failed to decode payload: {}", e))?;
        let payload: JwtPayload = serde_json::from_slice(&payload_bytes)
            .map_err(|e| format!("Failed to parse payload: {}", e))?;

        // Verify expiration
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|e| format!("System time error: {}", e))?
            .as_secs() as i64;

        if payload.exp < now {
            return Err("Token expired".to_string());
        }

        // Verify not-before
        if payload.nbf > now {
            return Err("Token not yet valid".to_string());
        }

        Ok(())
    }

    fn decode_payload(&self, token: &str) -> Result<JwtPayload, String> {
        let parts: Vec<&str> = token.split('.').collect();
        if parts.len() != 3 {
            return Err("Invalid token format".to_string());
        }

        let payload_bytes = base64_url_decode(parts[1])
            .map_err(|e| format!("Failed to decode payload: {}", e))?;
        serde_json::from_slice(&payload_bytes)
            .map_err(|e| format!("Failed to parse payload: {}", e))
    }

    fn get_user_entitlements(&self, user_id: &str) -> UserEntitlements {
        self.config
            .as_ref()
            .and_then(|c| c.data.get(user_id))
            .cloned()
            .unwrap_or_else(|| UserEntitlements {
                plan: "free".to_string(),
                permissions: vec![],
                roles: None,
            })
    }

    fn hmac_sha256(&self, key: &str, data: &str) -> Result<Vec<u8>, String> {
        let mut mac = HmacSha256::new_from_slice(key.as_bytes())
            .map_err(|e| format!("HMAC error: {}", e))?;
        mac.update(data.as_bytes());
        Ok(mac.finalize().into_bytes().to_vec())
    }

    fn send_json_response<T: Serialize>(&self, status_code: u32, data: &T) {
        match serde_json::to_vec(data) {
            Ok(body) => {
                self.send_http_response(
                    status_code,
                    vec![("Content-Type", "application/json")],
                    Some(&body)
                );
            }
            Err(e) => {
                proxy_wasm::hostcalls::log(
                    LogLevel::Error,
                    &format!("Failed to serialize response: {}", e)
                ).unwrap();
                self.send_http_response(
                    500,
                    vec![("Content-Type", "application/json")],
                    Some(b"{\"error\":\"internal server error\"}")
                );
            }
        }
    }
}

// Base64 URL-safe encoding/decoding helpers
fn base64_url_encode(data: &[u8]) -> String {
    general_purpose::URL_SAFE_NO_PAD.encode(data)
}

fn base64_url_decode(data: &str) -> Result<Vec<u8>, String> {
    general_purpose::URL_SAFE_NO_PAD
        .decode(data)
        .map_err(|e| format!("Base64 decode error: {}", e))
}
// [END serviceextensions_plugin_jwt_generator]
