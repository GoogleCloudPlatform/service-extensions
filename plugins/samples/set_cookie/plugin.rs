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

// [START serviceextensions_plugin_set_cookie]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use rand::rngs::SmallRng;
use rand::{RngCore, SeedableRng};

// Define the cookie name as a constant
const COOKIE_NAME: &str = "my_cookie";

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Info);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        let seed = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64;

        Box::new(MyRootContext {
            rng: SmallRng::seed_from_u64(seed),
        })
    });
}}

struct MyRootContext {
    rng: SmallRng,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn create_http_context(&self, _context_id: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            session_id: None,
            rng: self.rng.clone(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    session_id: Option<String>,
    rng: SmallRng,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Attempt to extract the session ID from the Cookie header
        self.session_id = self.get_session_id_from_cookie();

        Action::Continue
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        if let Some(ref session_id) = self.session_id {
            // Log the existing session ID
            log::info!(
                "This current request is for the existing session ID: {}",
                session_id
            );
        } else {
            // Generate a new session ID
            let new_session_id = self.generate_random_session_id().to_string();

            // Log the creation of a new session ID
            log::info!(
                "New session ID created for the current request: {}",
                new_session_id
            );

            // Set the Set-Cookie header with the new session ID
            self.add_http_response_header(
                "Set-Cookie",
                &format!("{}={}; Path=/; HttpOnly", COOKIE_NAME, new_session_id),
            );
        }

        Action::Continue
    }
}

impl MyHttpContext {
    /// Extracts the session ID from the Cookie header if present.
    fn get_session_id_from_cookie(&self) -> Option<String> {
        match self.get_http_request_header("Cookie") {
            Some(cookies) => {
                // Split the Cookie header into individual cookies
                for cookie in cookies.split("; ") {
                    let parts: Vec<&str> = cookie.splitn(2, '=').collect();
                    if parts.len() == 2 && parts[0] == COOKIE_NAME {
                        return Some(parts[1].to_string());
                    }
                }
                None
            }
            None => None,
        }
    }

    /// Generates a random `u32` session ID.
    fn generate_random_session_id(&mut self) -> u32 {
        self.rng.next_u32()
    }
}
// [END serviceextensions_plugin_set_cookie]
