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

// [START serviceextensions_plugin_country_query]
use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        // Try common CDN country headers
        const COUNTRY_HEADERS: [&str; 4] = [
            "x-country",
            "cloudfront-viewer-country", 
            "x-client-geo-location",
            "x-appengine-country",
        ];

        // Get country value from Cloud CDN headers or default to "unknown"
        let country_value = COUNTRY_HEADERS
            .iter()
            .find_map(|header| self.get_http_request_header(header))
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "unknown".to_string());

        // Log the country value for GCP logs
        info!("country: {}", country_value);

        // Get current path and add country query parameter
        let path = self.get_http_request_header(":path").unwrap_or_default();
        let new_path = if path.contains('?') {
            format!("{}&country={}", path, country_value)
        } else {
            format!("{}?country={}", path, country_value)
        };
        
        self.set_http_request_header(":path", Some(&new_path));

        Action::Continue
    }
}
// [END serviceextensions_plugin_country_query]
