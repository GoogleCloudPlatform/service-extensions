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

// [START serviceextensions_plugin_jwt_auth]
use chrono::{DateTime, Duration, Utc};
use jwt_compact::{alg::Rsa, AlgorithmExt, Empty, TimeOptions, UntrustedToken};
use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use rsa::{pkcs8::DecodePublicKey, RsaPublicKey};
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext { public_key: None })
    });
}}
struct MyRootContext {
    public_key: Option<Rc<RsaPublicKey>>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _plugin_configuration_size: usize) -> bool {
        // Fetch plugin config
        if let Some(config_data) = self.get_plugin_configuration() {
            if let Ok(config_str) = std::str::from_utf8(&config_data) {
                // Parse the RSA public key from PEM
                if let Ok(key) = RsaPublicKey::from_public_key_pem(config_str) {
                    self.public_key = Some(Rc::new(key));
                    return true;
                }
            }
        }
        false
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            public_key: self.public_key.clone(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    public_key: Option<Rc<RsaPublicKey>>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Retrieve the ":path" header
        let path = match self.get_http_request_header(":path") {
            Some(path) => path,
            None => return self.deny("Access forbidden - missing :path header."),
        };

        // Parse the URL
        let url_str = format!("http://example.com{}", path);
        let mut url = match url::Url::parse(&url_str) {
            Ok(url) => url,
            Err(_) => return self.deny("Access forbidden - invalid URL."),
        };

        // Get the query parameters
        let mut query_pairs = url
            .query_pairs()
            .into_owned()
            .collect::<Vec<(String, String)>>();
        let mut jwt_value = None;
        query_pairs.retain(|(key, value)| {
            if key == "jwt" {
                jwt_value = Some(value.clone());
                false // Remove 'jwt' from the query parameters
            } else {
                true
            }
        });

        // Check if the JWT token exists
        let jwt = match jwt_value {
            Some(jwt) => jwt,
            None => return self.deny("Access forbidden - missing token."),
        };

        // Check if the JWT token is valid
        let token = match UntrustedToken::new(&jwt) {
            Ok(token) => token,
            Err(_) => return self.deny("Access forbidden - invalid token."),
        };

        // Check if the JWT is allowed
        if !self.is_allowed(&token) {
            return self.deny("Access forbidden.");
        }

        // Strip the JWT from the URL after validation
        url.query_pairs_mut().clear().extend_pairs(query_pairs);
        let new_path = url.path().to_string();
        let new_query = url.query().unwrap_or("").to_string();
        let new_path_with_query = if new_query.is_empty() {
            new_path
        } else {
            format!("{}?{}", new_path, new_query)
        };
        self.set_http_request_header(":path", Some(&new_path_with_query));
        Action::Continue
    }
}

impl MyHttpContext {
    // Verifies the RS256 signature with the configured public key, then the
    // `exp` and `nbf` claims when present. Like the C++ sample, allows 60
    // seconds of clock skew.
    fn is_allowed(&self, token: &UntrustedToken) -> bool {
        let public_key = match &self.public_key {
            Some(public_key) => public_key,
            None => return false,
        };
        let token = match Rsa::rs256().validator::<Empty>(public_key).validate(token) {
            Ok(token) => token,
            Err(_) => return false,
        };
        let claims = token.claims();
        let now = DateTime::<Utc>::from(self.get_current_time());
        let time_options = TimeOptions::new(Duration::seconds(60), move || now);
        (claims.expiration.is_none() || claims.validate_expiration(&time_options).is_ok())
            && (claims.not_before.is_none() || claims.validate_maturity(&time_options).is_ok())
    }

    // Logs the reason and rejects the request with 403 Forbidden.
    fn deny(&self, reason: &str) -> Action {
        info!("{}", reason);
        self.send_http_response(403, vec![], Some(format!("{}\n", reason).as_bytes()));
        Action::Pause
    }
}
// [END serviceextensions_plugin_jwt_auth]
