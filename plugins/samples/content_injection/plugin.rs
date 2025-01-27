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

// [START serviceextensions_plugin_content_injection]
use lol_html::html_content::ContentType;
use lol_html::*;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::cell::RefCell;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { MyHttpContext::new()});
}}

struct MyHttpContext<'a> {
    // Stores HTML as rewriter parses and modifies HTML.
    // Only stores completed sections(e.g., when rewriter parses "<di", output
    // will be empty until the next chunk comes in. If the next chunk was
    // "v> <h1>foo</h", the output will then contain "<div><h1>foo" ).
    output: Rc<RefCell<Vec<u8>>>,
    // HTML rewriter. Member of MyHttpContext a.k.a "StreamContext" so that the
    // rewriter persists across multiple body callbacks.
    rewriter: Option<HtmlRewriter<'a, Box<dyn FnMut(&[u8])>>>,
    // True when plugin has added script to <head>.
    completed: Rc<RefCell<bool>>,
}

impl<'a> MyHttpContext<'a> {
    pub fn new() -> Box<MyHttpContext<'a>> {
        let output = Rc::new(RefCell::new(Vec::new()));
        let completed = Rc::new(RefCell::new(false));
        Box::new(MyHttpContext {
            output: output.clone(),
            completed: completed.clone(),
            rewriter: Some(HtmlRewriter::new(
                Settings {
                    element_content_handlers: vec![element!("head", move |el| {
                        el.prepend(
                            "<script src=\"https://www.foo.com/api.js\"></script>",
                            ContentType::Html,
                        );
                        *completed.borrow_mut() = true;
                        Ok(())
                    })],
                    ..Settings::new()
                },
                Box::new(move |c: &[u8]| output.borrow_mut().extend_from_slice(c)),
            )),
        })
    }
}

impl<'a> Context for MyHttpContext<'a> {}

impl<'a> HttpContext for MyHttpContext<'a> {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        return Action::Continue;
    }

    fn on_http_response_body(&mut self, body_size: usize, _: bool) -> Action {
        if *self.completed.borrow() == true {
            // Return immediately if plugin is "done" to avoid unnecessary work
            // and resource usage.
            return Action::Continue;
        }
        if let Some(body_bytes) = self.get_http_response_body(0, body_size) {
            let existing_output = self.output.borrow().clone();
            // Parse/rewrite current chunk
            self.rewriter.as_mut().unwrap().write(&body_bytes).unwrap();
            if *self.completed.borrow() == true {
                // Stop the rewriter after completing desired domain rewrite to
                // dump any unparsable inputs to output.
                self.rewriter.take().expect("msg").end().unwrap();
            }
            let diff = self.output.borrow().as_slice()[existing_output.len()..].to_vec();
            self.set_http_response_body(0, body_size, diff.as_slice());
        }
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_content_injection]
