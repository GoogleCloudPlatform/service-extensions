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

// [START serviceextensions_plugin_hmac_authtoken]
use hex;
use hmac::{Hmac, Mac};
use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use sha2::Sha256;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

// Replace with your desired values.
const SECRET_KEY: &[u8] = b"your_secret_key";
const TOKEN_NAME: &str = "token";

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        let path = self.get_http_request_header(":path");

        // Parse the URL
        let url_str = format!("http://example.com{}", path.unwrap_or_default());
        let mut url = match url::Url::parse(&url_str) {
            Ok(url) => url,
            Err(e) => {
                info!("Error parsing the :path HTTP header: {0}", e);
                self.send_http_response(
                    400,
                    vec![],
                    Some(b"Error parsing the :path HTTP header.\n"),
                );
                return Action::Pause;
            }
        };

        // Get the query parameters
        let mut query_pairs = url
            .query_pairs()
            .into_owned()
            .collect::<Vec<(String, String)>>();
        let mut auth_token_value = None;
        query_pairs.retain(|(key, value)| {
            if key == TOKEN_NAME {
                auth_token_value = Some(value.clone());
                false // Remove 'token' from the query parameters
            } else {
                true
            }
        });

        // Check if the HMAC token exists.
        let auth_token = match auth_token_value {
            Some(auth_token) => auth_token,
            None => {
                info!("Access forbidden - missing token.");
                self.send_http_response(403, vec![], Some(b"Access forbidden - missing token.\n"));
                return Action::Pause;
            }
        };

        // Strip the token from the URL.
        url.query_pairs_mut().clear().extend_pairs(query_pairs);
        let new_path = url.path().to_string();
        let new_query = url.query().unwrap_or_default();
        let new_path_with_query = if new_query.is_empty() {
            new_path
        } else {
            format!("{}?{}", new_path, new_query)
        };

        // Compare if the generated signature matches the token sent.
        // In this sample the signature is generated using the request :path.
        if !check_hmac_signature(&new_path_with_query, &auth_token) {
            info!("Access forbidden - invalid token.");
            self.send_http_response(403, vec![], Some(b"Access forbidden - invalid token.\n"));
            return Action::Pause;
        }

        self.set_http_request_header(":path", Some(&new_path_with_query));
        Action::Continue
    }
}

fn check_hmac_signature(data: &str, token: &str) -> bool {
    let mut mac =
        Hmac::<Sha256>::new_from_slice(SECRET_KEY).expect("HMAC can take key of any size");
    mac.update(data.as_bytes());
    let token_bytes = hex::decode(token).unwrap_or_default();
    mac.verify_slice(&token_bytes[..]).is_ok()
}
// [END serviceextensions_plugin_hmac_authtoken]
