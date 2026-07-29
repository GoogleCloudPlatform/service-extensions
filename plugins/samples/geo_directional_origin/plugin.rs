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

// [START serviceextensions_plugin_geo_routing]
use proxy_wasm::traits::{Context, HttpContext};
use proxy_wasm::types::{Action, LogLevel};

const CLIENT_REGION_PROPERTY: &[&str] = &["source", "client_region"];
const COUNTRY_CODE_HEADER: &str = "x-country-code";

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> {
        Box::new(MyHttpContext)
    });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

impl MyHttpContext {
    #[inline]
    fn set_geo_header(&mut self, property: &[&str], header: &str) {
        if let Some(bytes) = self.get_property(property.to_vec()) {
            if let Ok(value) = std::str::from_utf8(&bytes) {
                if !value.is_empty() {
                    self.set_http_request_header(header, Some(value));
                    return;
                }
            }
        }
        self.set_http_request_header(header, None);
    }
}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        self.set_geo_header(CLIENT_REGION_PROPERTY, COUNTRY_CODE_HEADER);
        Action::Continue
    }
}
// [END serviceextensions_plugin_geo_routing]
