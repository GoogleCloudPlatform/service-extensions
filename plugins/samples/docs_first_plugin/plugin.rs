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

// [START serviceextensions_plugin_docs_first_plugin]
use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! { {
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
} }

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        info!("onRequestHeaders: hello from wasm");

        // Route extension example: host rewrite
        self.set_http_request_header(":authority", Some("service-extensions.com"));
        self.set_http_request_header(":path", Some("/"));
        return Action::Continue;
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        info!("onResponseHeaders: hello from wasm");

        // Traffic extension example: add response header
        self.add_http_response_header("hello", "service-extensions");
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_docs_first_plugin]
