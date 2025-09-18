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

// [START serviceextensions_plugin_hmac_token_validation]
use log::{debug, info, warn};
use proxy_wasm::{
    traits::{Context, HttpContext, RootContext},
    types::{Action, LogLevel},
};
use std::time::{SystemTime, UNIX_EPOCH};

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Debug);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(HmacValidationRootContext {
            secret_key: "your-secret-key".into(),
            token_validity_seconds: 300,
        })
    });
}}

struct HmacValidationRootContext {
    secret_key: String,
    token_validity_seconds: u64,
}

impl Context for HmacValidationRootContext {}

impl RootContext for HmacValidationRootContext {
    fn get_type(&self) -> Option<proxy_wasm::types::ContextType> {
        Some(proxy_wasm::types::ContextType::HttpContext)
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(HmacValidationContext {
            secret_key: self.secret_key.clone(),
            token_validity_seconds: self.token_validity_seconds,
        }))
    }
}

struct HmacValidationContext {
    secret_key: String,
    token_validity_seconds: u64,
}

impl HmacValidationContext {
    fn send_error_response(&self, status: u32, body: &'static str, headers: Vec<(&str, &str)>) -> Action {
        self.send_http_response(
            status,
            headers,
            Some(body.as_bytes()),
        );
        Action::Pause
    }

    fn validate_token(&self, auth_header: &str) -> Result<(), Action> {
        if auth_header.len() < 5 || !auth_header[..5].eq_ignore_ascii_case("HMAC ") {
            return Err(self.send_error_response(400, "Invalid Authorization scheme. Use 'HMAC'", vec![]));
        }

        let token = &auth_header[5..];
        let (timestamp_str, provided_hmac) = token.split_once(':').ok_or_else(|| 
            self.send_error_response(400, "Invalid token format: expected 'timestamp:hmac'", vec![])
        )?;

        let timestamp = timestamp_str.parse::<i64>().map_err(|_| 
            self.send_error_response(400, "Invalid timestamp", vec![])
        )?;

        let current_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(i64::MAX);

        if (current_time - timestamp).abs() > self.token_validity_seconds as i64 {
            return Err(self.send_error_response(403, "Token expired", vec![]));
        }

        let method = self.get_http_request_header(":method")
            .ok_or_else(|| self.send_error_response(400, "Missing :method header", vec![]))?;

        let path = self.get_http_request_header(":path")
            .ok_or_else(|| self.send_error_response(400, "Missing :path header", vec![]))?;

        let message = format!("{}:{}:{}", method, path, timestamp_str);
        let computed_hmac = compute_md5(&format!("{}{}", self.secret_key, message));

        debug!(
            "HMAC validation: method={} path={} timestamp={} received={} expected={}",
            method, path, timestamp_str, provided_hmac, computed_hmac
        );

        if computed_hmac != provided_hmac {
            let client_ip = self.get_http_request_header("x-forwarded-for").unwrap_or_default();
            warn!("Invalid HMAC from {}", client_ip);
            Err(self.send_error_response(403, "Invalid HMAC", vec![]))
        } else {
            info!("Valid HMAC for path: {}", path);
            Ok(())
        }
    }
}

impl Context for HmacValidationContext {}

impl HttpContext for HmacValidationContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        match self.get_http_request_header("authorization") {
            Some(auth_header) => self.validate_token(&auth_header)
                .and(Ok(Action::Continue))
                .unwrap_or(Action::Pause),
            None => self.send_error_response(
                401, 
                "Missing Authorization header", 
                vec![("WWW-Authenticate", "HMAC realm=\"api\"")]
            ),
        }
    }
}

fn compute_md5(input: &str) -> String {
    let digest = md5::compute(input);
    format!("{:x}", digest)
}
// [END serviceextensions_plugin_hmac_token_validation]