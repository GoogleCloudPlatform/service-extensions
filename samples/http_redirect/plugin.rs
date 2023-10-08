// Copyright 2023 Google LLC
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

use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use url::Url;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        let Some(path) = self.get_http_request_header(":path") else {
            // This standard Envoy pseudo-header should always be present.
            return Action::Continue
        };
        // Url requires a base for parsing relative URLs.
        let base = Url::parse("http://www.example.com").ok();
        let options = Url::options().base_url(base.as_ref());
        let Ok(url) = options.parse(&path) else {
            // Don't try to redirect on a malformed URL.
            return Action::Continue
        };
        let redirect = match url.path() {
            "/index.php" => base,
            _ => None
        };
        if let Some(redirect_url) = redirect {
            self.send_http_response(301, vec![("Location", redirect_url.as_str())], None);
        }
        Action::Continue
    }
}
