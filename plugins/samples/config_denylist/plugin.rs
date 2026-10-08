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

// [START serviceextensions_plugin_example_config_denylist]
use log::*;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::collections::HashSet;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext {
            tokens: Rc::new(HashSet::new()),
        })
    });
}}

struct MyRootContext {
    // NOTE: with better lifetime annotations we might avoid these String copies.
    tokens: Rc<HashSet<String>>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        if let Some(config) = self.get_plugin_configuration() {
            // Config file contains a single bad token per line.
            let config_lines = String::from_utf8(config).unwrap();
            let mut keys = HashSet::new();
            for line in config_lines.lines() {
                let key = line.trim();
                if !key.is_empty() {
                    keys.insert(key.to_string());
                }
            }
            self.tokens = Rc::new(keys);
        }
        info!("Config keys size {0}", self.tokens.len());
        return true;
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            // Important - this is a shallow copy of the set, doing the deep copy will cause
            // tokens to be copied in every request. Cloning a big set at this point will
            // cause timeouts and 500 Internal Server Error response.
            tokens: self.tokens.clone(),
        }))
    }
    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    tokens: Rc<HashSet<String>>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        match self.get_http_request_header("User-Token") {
            None => {
                self.send_http_response(403, vec![], Some(b"Access forbidden - token missing.\n"));
                Action::Pause
            }
            Some(auth_header) => {
                if self.tokens.contains(&auth_header) {
                    self.send_http_response(403, vec![], Some(b"Access forbidden.\n"));
                    Action::Pause
                } else {
                    Action::Continue
                }
            }
        }
    }
    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_example_config_denylist]
