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

// [START serviceextensions_plugin_normalize_header]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

const DEVICE_TYPE_KEY: &str = "client-device-type";
const DEVICE_TYPE_VALUE: &str = "mobile";

// Determines client device type based on request headers.
impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Change the key and value according to your needs.
        let mobile_header = self.get_http_request_header("Sec-CH-UA-Mobile");
        if mobile_header.unwrap_or_default() == "?1" {
            self.add_http_request_header(DEVICE_TYPE_KEY, DEVICE_TYPE_VALUE);
            return Action::Continue;
        }

        // Check "User-Agent" header for mobile substring (case insensitive)
        let user_agent = self.get_http_request_header("User-Agent");
        if user_agent.map_or(false, |s| s.to_lowercase().contains(DEVICE_TYPE_VALUE)) {
            self.add_http_request_header(DEVICE_TYPE_KEY, DEVICE_TYPE_VALUE);
            return Action::Continue;
        }

        // No specific device type identified, set to "unknown"
        self.add_http_request_header(DEVICE_TYPE_KEY, "unknown");
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_normalize_header]
