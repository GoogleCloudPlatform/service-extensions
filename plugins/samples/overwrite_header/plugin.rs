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

// [START serviceextensions_plugin_overwrite_header]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

// This sample replaces an HTTP header with the given key and value.
// Unlike `add_http_request_header` which appends values to existing headers,
// this plugin overwrites the entire value for the specified key if the
// header already exists or create it with the new value.
impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Change the key and value according to your needs.
        let header_key = "RequestHeader";
        if let Some(_header) = self.get_http_request_header(header_key) {
            self.set_http_request_header(header_key, Some("changed"));
        }
        return Action::Continue;
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        // Unlike the previous example, the header will be added if it doesn't exist
        // or updated if it already does.
        // Change the key and value according to your needs.
        self.set_http_response_header("ResponseHeader", Some("changed"));
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_overwrite_header]
