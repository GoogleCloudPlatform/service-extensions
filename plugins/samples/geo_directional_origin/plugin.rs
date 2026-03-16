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

const CLIENT_REGION_PROPERTY: &[&str] = &["request", "client_region"];
const COUNTRY_CODE_HEADER: &str = "x-country-code";

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> {
        Box::new(GeoRoutingContext)
    });
}}

struct GeoRoutingContext;

impl Context for GeoRoutingContext {}

impl HttpContext for GeoRoutingContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        if let Some(country_bytes) = self.get_property(CLIENT_REGION_PROPERTY.to_vec()) {
            if let Ok(country_code) = std::str::from_utf8(&country_bytes) {
                if !country_code.is_empty() {
                    self.set_http_request_header(COUNTRY_CODE_HEADER, Some(country_code));
                    return Action::Continue;
                }
            }
        }

        self.set_http_request_header(COUNTRY_CODE_HEADER, None);

        Action::Continue
    }
}
// [END serviceextensions_plugin_geo_routing]
