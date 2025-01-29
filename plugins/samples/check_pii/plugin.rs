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

// [START serviceextensions_plugin_check_pii]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use regex::Regex;
use std::borrow::Cow;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext::new())
    });
}}

struct MyRootContext {
    card_matcher: Option<Rc<Regex>>,
    code10_matcher: Option<Rc<Regex>>,
}

impl MyRootContext {
    fn new() -> Self {
        MyRootContext {
            card_matcher: None,
            code10_matcher: None,
        }
    }
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _config_size: usize) -> bool {
        // Credit card numbers in 16-digit hyphenated format.
        let card_regex = Regex::new(r"\d{4}-\d{4}-\d{4}-(\d{4})");
        if card_regex.is_err() {
            return false;
        }

        // 10-digit numeric codes.
        let code10_regex = Regex::new(r"\d{7}(\d{3})");
        if code10_regex.is_err() {
            return false;
        }

        self.card_matcher = Some(Rc::new(card_regex.unwrap()));
        self.code10_matcher = Some(Rc::new(code10_regex.unwrap()));

        true
    }

    fn create_http_context(&self, context_id: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext::new(
            self.card_matcher.clone(),
            self.code10_matcher.clone(),
        )))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    card_matcher: Option<Rc<Regex>>,
    code10_matcher: Option<Rc<Regex>>,
}

impl MyHttpContext {
    fn new(
        card_matcher: Option<Rc<Regex>>,
        code10_matcher: Option<Rc<Regex>>,
    ) -> Self {
        MyHttpContext {
            card_matcher,
            code10_matcher,
        }
    }

    /// Mask credit card and 10-digit codes in-place on a given string,
    /// returning `true` if modifications occurred.
    fn mask_pii(&self, text: &mut String) -> bool {
        let mut modified = false;

        if let Some(ref card_re) = self.card_matcher {
            // Mask credit card numbers: XXXX-XXXX-XXXX-$1
            let replaced = card_re.replace_all(text, "XXXX-XXXX-XXXX-$1");
            if replaced != Cow::Borrowed(text.as_str()) {
                *text = replaced.to_string();
                modified = true;
            }
        }

        if let Some(ref code10_re) = self.code10_matcher {
            // Mask 10-digit codes: XXXXXXX$1
            let replaced = code10_re.replace_all(text, "XXXXXXX$1");
            if replaced != Cow::Borrowed(text.as_str()) {
                *text = replaced.to_string();
                modified = true;
            }
        }

        modified
    }
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    /// Sets `Accept-Encoding: identity` to avoid compressed responses.
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        self.set_http_request_header("accept-encoding", Some("identity"));
        Action::Continue
    }

    /// Mask PII in each header value.
    fn on_http_response_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        let old_headers = self.get_http_response_headers();

        let mut changed = false;
        let mut updated_headers = Vec::with_capacity(old_headers.len());

        for (name, value) in old_headers {
            let mut new_value = value;
            if self.mask_pii(&mut new_value) {
                changed = true;
            }
            updated_headers.push((name, new_value));
        }

        if changed {
            let new_headers_refs: Vec<(&str, &str)> = updated_headers
                .iter()
                .map(|(n, v)| (n.as_str(), v.as_str()))
                .collect();

            self.set_http_response_headers(new_headers_refs);
        }

        Action::Continue
    }

    /// Mask PII in the body buffer (if not empty).
    fn on_http_response_body(&mut self, body_size: usize, _end_of_stream: bool) -> Action {
        if let Some(mut body_bytes) = self.get_http_response_body(0, body_size) {
            let mut body_string = String::from_utf8_lossy(&body_bytes).to_string();

            if self.mask_pii(&mut body_string) {
                self.set_http_response_body(0, body_string.len(), body_string.as_bytes());
            }
        }

        Action::Continue
    }
}
// [END serviceextensions_plugin_check_pii]