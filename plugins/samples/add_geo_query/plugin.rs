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

// [START serviceextensions_plugin_country_query]
use proxy_wasm::traits::{Context, HttpContext};
use proxy_wasm::types::{Action, LogLevel};

const CLIENT_REGION_PATH: &[&str] = &["request", "client_region"];
const DEFAULT_COUNTRY: &str = "unknown";

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        let country_value = self.get_country_value();

        log::info!("country: {}", country_value);

        let path = self.get_http_request_header(":path").unwrap_or_default();
        let new_path = self.add_country_parameter(&path, &country_value);
        
        self.set_http_request_header(":path", Some(&new_path));

        Action::Continue
    }
}

impl MyHttpContext {
    fn get_country_value(&self) -> String {
        if let Some(bytes) = self.get_property(CLIENT_REGION_PATH.to_vec()) {
            if let Ok(country) = String::from_utf8(bytes) {
                if !country.is_empty() {
                    return country;
                }
            }
        }
        DEFAULT_COUNTRY.to_string()
    }

    fn add_country_parameter(&self, path: &str, country: &str) -> String {
        let mut new_path = String::with_capacity(path.len() + country.len() + 10);
        new_path.push_str(path);

        if path.contains('?') {
            new_path.push_str("&country=");
        } else {
            new_path.push_str("?country=");
        }
        new_path.push_str(country);

        new_path
    }
}
// [END serviceextensions_plugin_country_query]
