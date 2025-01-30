// // Copyright 2025 Google LLC
// //
// // Licensed under the Apache License, Version 2.0 (the "License");
// // you may not use this file except in compliance with the License.
// // You may obtain a copy of the License at
// //
// //     http://www.apache.org/licenses/LICENSE-2.0
// //
// // Unless required by applicable law or agreed to in writing, software
// // distributed under the License is distributed on an "AS IS" BASIS,
// // WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// // See the License for the specific language governing permissions and
// // limitations under the License.a

// [START serviceextensions_plugin_redirect]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

const OLD_PATH_PREFIX: &str = "/foo/";
const NEW_PATH_PREFIX: &str = "/bar/";

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
}}

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        // Get the ":path" header value.
        if let Some(path) = self.get_http_request_header(":path") {
            // Check if the path starts with the OLD_PATH_PREFIX.
            if path.starts_with(OLD_PATH_PREFIX) {
                // Construct the new path by replacing the prefix.
                let new_path = format!("{}{}", NEW_PATH_PREFIX, &path[OLD_PATH_PREFIX.len()..]);

                // Send a 301 response with the new location.
                self.send_http_response(
                    301,
                    vec![("Location", new_path.as_str())],
                    Some(format!("Content moved to {}", new_path).as_bytes()),
                );

                return Action::Pause; // End stream and stop further processing.
            }
        }
        Action::Continue
    }
}
// [END serviceextensions_plugin_redirect]
