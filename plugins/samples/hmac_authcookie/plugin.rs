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

// [START serviceextensions_plugin_hmac_authcookie]
use cookie::Cookie;
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
const COOKIE_NAME: &str = "Authorization";

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        let cookies = self.get_http_request_header("Cookie").unwrap_or_default();

        // Check if the HMAC token exists.
        let auth_token = match get_token_from_cookie(&cookies) {
            Some(auth_token) => auth_token,
            None => {
                info!("Access forbidden - missing HMAC cookie.");
                self.send_http_response(
                    403,
                    vec![],
                    Some(b"Access forbidden - missing HMAC cookie.\n"),
                );
                return Action::Pause;
            }
        };

        // Compare if the generated signature matches the token sent.
        // In this sample the signature is generated using the request :path.
        let path = self.get_http_request_header(":path").unwrap_or_default();
        if !check_hmac_signature(&path, &auth_token) {
            info!("Access forbidden - invalid HMAC cookie.");
            self.send_http_response(
                403,
                vec![],
                Some(b"Access forbidden - invalid HMAC cookie.\n"),
            );
            return Action::Pause;
        }

        Action::Continue
    }
}

fn get_token_from_cookie(cookies: &str) -> Option<String> {
    for cookie in Cookie::split_parse(cookies) {
        let cookie = cookie.unwrap();
        if cookie.name() == COOKIE_NAME {
            return Some(cookie.value().to_owned());
        }
    }
    None
}

fn check_hmac_signature(data: &str, token: &str) -> bool {
    let mut mac =
        Hmac::<Sha256>::new_from_slice(SECRET_KEY).expect("HMAC can take key of any size");
    mac.update(data.as_bytes());
    let token_bytes = hex::decode(token).unwrap_or_default();
    mac.verify_slice(&token_bytes[..]).is_ok()
}
// [END serviceextensions_plugin_hmac_authcookie]
