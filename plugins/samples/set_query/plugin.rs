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

// [START serviceextensions_plugin_set_query]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use url::Position;
use url::Url;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);  // log everything, subject to plugin LogConfig
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        if let Some(path) = self.get_http_request_header(":path") {
            // Create dummy base/host to allow parsing relative paths.
            let base = Url::parse("http://example.com").ok();
            let options = Url::options().base_url(base.as_ref());
            if let Ok(url) = options.parse(&path) {
                let query = url.query_pairs().filter(|(k, _)| k != "key");
                let mut edit = url.clone();
                edit.query_pairs_mut()
                    .clear()
                    .extend_pairs(query)
                    .append_pair("key", "new val");
                self.set_http_request_header(":path", Some(&edit[Position::BeforePath..]));
            };
        }
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_set_query]
