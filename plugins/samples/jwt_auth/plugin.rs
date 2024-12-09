// Copyright 2024 Google LLC
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
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use jwt_compact::{alg::Rsa, UntrustedToken, Algorithm, AlgorithmExt};
use rsa::{pkcs8::DecodePublicKey, RsaPublicKey};

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext { public_key: None })
    });
}}
struct MyRootContext {
    public_key: Option<RsaPublicKey>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _plugin_configuration_size: usize) -> bool {
        // Fetch plugin config
        if let Some(config_data) = self.get_plugin_configuration() {
            if let Ok(config_str) = std::str::from_utf8(&config_data) {
                // Parse the RSA public key from PEM
                if let Ok(key) = RsaPublicKey::from_public_key_pem(config_str) {
                    self.public_key = Some(key);
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
    public_key: Option<RsaPublicKey>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Retrieve the ":path" header
        let path = match self.get_http_request_header(":path") {
            Some(path) => path,
            None => {
                self.send_http_response(
                    403,
                    vec![],
                    Some(b"Access forbidden - missing :path header.\n"),
                );
                return Action::Pause;
            }
        };

        // Parse the URL
        let url_str = format!("http://example.com{}", path);
        let mut url = match url::Url::parse(&url_str) {
            Ok(url) => url,
            Err(_) => {
                self.send_http_response(
                    403,
                    vec![],
                    Some(b"Access forbidden - invalid URL.\n"),
                );
                return Action::Pause;
            }
        };

        // Get the query parameters
        let mut query_pairs = url.query_pairs().into_owned().collect::<Vec<(String, String)>>();
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
            None => {
                self.send_http_response(
                    403,
                    vec![],
                    Some(b"Access forbidden - missing token.\n"),
                );
                return Action::Pause;
            }
        };

        // Validate the JWT
        match self.verify_jwt(&jwt) {
            Ok(()) => {
                // JWT is valid, remove it from the path
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
            Err(e) => {
                self.send_http_response(
                    403,
                    vec![],
                    Some(e.as_bytes()),
                );
                Action::Pause
            }
        }
    }
}

impl MyHttpContext {

    fn verify_jwt(&self, token_str: &str) -> Result<(), String> {

        let public_key = self.public_key.as_ref().ok_or("Public key not found".to_string())?;

        // Create the RS256 algorithm
        let rsa_alg = Rsa::rs256();

        // Parse the token
        let token = UntrustedToken::new(token_str)
            .map_err(|_| "Access forbidden - invalid token.".to_string())?;

        // Check if the algorithm in the token matches RS256
        if token.algorithm() != rsa_alg.name() {
            return Err("Unexpected algorithm".to_string());
        }

        // Validate the token
        rsa_alg
            .validator::<()>(public_key)
            .validate(&token)
            .map_err(|_| "Access forbidden - Jwt verification fails.".to_string())?;

        Ok(())
    }
}
// [END serviceextensions_plugin_jwt_auth]