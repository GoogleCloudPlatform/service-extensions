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

// [START serviceextensions_plugin_ab_testing]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use url::Url;

const A_PATH: &str = "/v1/";
const B_PATH: &str = "/v2/";
const PERCENTILE: u64 = 50;

proxy_wasm::main! {{
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        if let Some(path) = self.get_http_request_header(":path") {
            let user = extract_user_from_path(&path);
            // Check if path starts with /v1/, has a user param, and hash falls into the percentile
            if path.to_ascii_lowercase().starts_with(A_PATH) && !user.is_empty() && should_use_v2(&user) {
                let new_path = format!("{}{}", B_PATH, &path[A_PATH.len()..]);
                self.set_http_request_header(":path", Some(&new_path));
            }
        }
        Action::Continue
    }
}

// Extract the "user" query parameter from the path.
fn extract_user_from_path(path: &str) -> String {
    let full_url = format!("http://example.com{}", path);
    if let Ok(url) = Url::parse(&full_url) {
        if let Some(_query_pairs) = url.query() {
            let pairs = url.query_pairs();
            for (key, value) in pairs {
                if key == "user" {
                    return value.to_string();
                }
            }
        }
    }
    "".to_string()
}

// Compute hash of `user` and determine if it falls into the given percentile
fn should_use_v2(user: &str) -> bool {
    // Calculate a deterministic hash from user.
    // Sum the ASCII values of the characters and then offset by length.
    let sum: u64 = user.bytes().map(u64::from).sum();
    // Adjusting by length ensures different users fall into distinct ranges.
    let hash_value = (sum + (user.len() as u64 * 3)) % 100;

    hash_value <= PERCENTILE
}
// [END serviceextensions_plugin_ab_testing]