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

// [START serviceextensions_plugin_example_testing]
use log::*;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::time::SystemTime;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|context_id: u32, _| -> Box<dyn HttpContext> {
        Box::new(MyHttpContext { context_id })
    });
}}

struct MyHttpContext {
    context_id: u32,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        debug!("request headers {}", self.context_id);
        return Action::Continue;
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        debug!("response headers {}", self.context_id);

        // Emit some timestamps.
        for i in 1..4 {
            let ns = SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            info!("time {}: {}", i, ns);
        }

        // Conditionally reply with an error.
        if self.get_http_response_header("reply-with-error").is_some() {
            self.send_http_response(500, vec![("error", "goaway")], Some(b"fake error"));
            return Action::Pause;
        }
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_example_testing]
