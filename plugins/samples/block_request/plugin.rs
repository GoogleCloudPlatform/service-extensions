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

// [START serviceextensions_plugin_block_request]
use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use uuid::Uuid;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

const ALLOWED_REFERER: &str = "safe-site.com";

// Checks whether the client's Referer header matches an expected domain. If
// not, generate a 403 Forbidden response.
impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Check if referer match with the expected domain.
        let referer = self.get_http_request_header("Referer");
        if referer.map_or(true, |r| !r.contains(ALLOWED_REFERER)) {
            let request_id = Uuid::new_v4().simple();
            self.send_http_response(
                403,
                vec![],
                Some(format!("Forbidden - Request ID: {}", request_id).as_bytes()),
            );
            info!("Forbidden - Request ID: {}", request_id);
            return Action::Pause;
        }

        // Change it to a meaningful name according to your needs.
        self.add_http_request_header("my-plugin-allowed", "true");
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_block_request]
