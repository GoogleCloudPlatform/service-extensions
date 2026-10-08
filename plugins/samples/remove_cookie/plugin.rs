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

// [START serviceextensions_plugin_remove_setcookie]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(RemoveCookieContext) });
}}

struct RemoveCookieContext;

impl Context for RemoveCookieContext {}

impl HttpContext for RemoveCookieContext {
    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        // Remove all Set-Cookie headers from the response
        self.set_http_response_header("Set-Cookie", None);
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_remove_setcookie]