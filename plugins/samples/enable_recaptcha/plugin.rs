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

// [START serviceextensions_plugin_enable_recaptcha]

// Warning: This plugin simply shows that by adding scripts, one could enable a
// reCAPTCHA challenge. This is not a replacement for reading reCAPTCHA
// documentaion or following all user guide instructions. Please follow official
// reCAPTCHA documentation at https://developers.google.com/recaptcha.
use lol_html::html_content::ContentType;
use lol_html::*;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::cell::RefCell;
use std::error::Error;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
      Box::new(MyRootContext {
          recaptcha_key: Rc::new(RefCell::new(String::new())),
      })
    });
}}

struct MyRootContext {
    recaptcha_key: Rc<RefCell<String>>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        if let Some(config) = self.get_plugin_configuration() {
            // Config file contains only the recaptcha key.
            // Use of .unwrap() is fine here, since failure in on_configure
            // should result in plugin crash.
            let config_lines = String::from_utf8(config).unwrap();
            self.recaptcha_key = Rc::new(RefCell::new(config_lines));
        }
        return true;
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext::new(self.recaptcha_key.clone())))
    }
    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyOutputSink {
    // Stores HTML as the rewriter parses and modifies HTML.
    // Only stores sections of HTML that have not yet been seen back to client.
    // After sending data to client, we clear output to avoid unnecessary memory
    // growth.
    // See comment in MyHttpContext about use of Rc<RefCell<T>>.
    output_sink: Rc<RefCell<Vec<u8>>>,
}

impl OutputSink for MyOutputSink {
    fn handle_chunk(&mut self, chunk: &[u8]) {
        self.output_sink.borrow_mut().extend_from_slice(chunk);
    }
}

struct MyHttpContext<'a> {
    // Some member variables need to be wrapped in Rc<Refcell<T>> so that we can
    // modify the variable in multiple places as well as share ownership.
    // By using Rc, we are allowing multiple references to the same obeject to
    // exist at the same time.
    // By using Refcell, we are evaluating borrow checks at runtime, thus we are
    // commiting to not modfying the variable in multiple places simultaneously,
    // otherwise the code will panic and plugin will crash.

    // Stores HTML as the rewriter parses and modifies HTML.
    // Only stores sections of HTML that have not yet been seen back to client.
    // After sending data to client, we clear output to avoid unnecessary memory
    // growth.
    output: Rc<RefCell<Vec<u8>>>,
    // HtmlRewriter. Member of MyHttpContext a.k.a "StreamContext" so that the
    // rewriter persists across multiple body callbacks.The rewriter parses
    // and modifies chunks of Html. Behavior for Html modifications are defined
    // via content_handlers. The rewriter only writes completed sections of Html to
    // the output sink(e.g., when the rewriter parses "<di", nothing will be
    // sent to the output sink. If the next chunk was "v> <h1>foo</h", the
    // rewriter would then write "<div><h1>foo" to the output sink) unless
    // HtmlRewriter::end() is called. HtmlRewriter::end() results in all
    // uncompleted Html being buffered in rewriter to be sent to output sink as
    // if it were plain text.
    rewriter: Option<HtmlRewriter<'a, MyOutputSink>>,
    // True when plugin has added script to <head>.
    completed_script_injection: Rc<RefCell<bool>>,
    // reCaptcha site key
    recaptcha_key: Rc<RefCell<String>>,
}

impl<'a> MyHttpContext<'a> {
    pub fn new(key: Rc<RefCell<String>>) -> MyHttpContext<'a> {
        let output = Rc::new(RefCell::new(Vec::new()));
        let completed_script_injection = Rc::new(RefCell::new(false));
        let recaptcha_key = key;
        MyHttpContext {
            output: output.clone(),
            completed_script_injection: completed_script_injection.clone(),
            recaptcha_key: recaptcha_key.clone(),
            rewriter: Some(HtmlRewriter::new(
                Settings {
                    element_content_handlers: vec![element!("head", move |el| {
                        el.prepend(
                            format!("\n<script src=\"https://www.google.com/recaptcha/enterprise.js?render={}\"></script>\n", *recaptcha_key.borrow_mut()).as_str(),
                            ContentType::Html,
                            );
                        *completed_script_injection.borrow_mut() = true;
                        Ok(())
                    })],
                    ..Settings::new()
                },
                MyOutputSink {
                    output_sink: output,
                },
            )),
        }
    }

    fn parse_chunk(&mut self, body_bytes: Bytes) -> Result<(), Box<dyn Error>> {
        // Parse/rewrite current chunk
        self.rewriter
            .as_mut()
            .ok_or("Expected valid rewriter. Got None")?
            .write(&body_bytes)?;
        return Ok(());
    }

    fn end_rewriter(&mut self) -> Result<(), Box<dyn Error>> {
        // Stop the rewriter after completing desired domain rewrite to
        // dump any unparsable inputs to output.
        self.rewriter
            .take()
            .expect("Expected valid rewriter. Got None")
            .end()?;
        return Ok(());
    }
}

impl<'a> Context for MyHttpContext<'a> {}

impl<'a> HttpContext for MyHttpContext<'a> {
    fn on_http_response_body(&mut self, body_size: usize, _: bool) -> Action {
        let chunk_size = 500;
        if *self.completed_script_injection.borrow() {
            // Return immediately if plugin is "done" to avoid unnecessary work
            // and resource usage.
            return Action::Continue;
        }
        for start_index in (0..body_size).step_by(chunk_size) {
            if let Some(body_bytes) = self.get_http_response_body(start_index, chunk_size) {
                if let Err(e) = self.parse_chunk(body_bytes) {
                    // Prefer sending immediate response instead of panicking to avoid plugin crashes.
                    self.send_http_response(
                        500,
                        vec![],
                        Some(
                            &format!("Error while writing to HtmlRewriter: {}", e.to_string())
                                .into_bytes(),
                        ),
                    );
                    return Action::Pause;
                }
                if *self.completed_script_injection.borrow() {
                    if let Err(e) = self.end_rewriter() {
                        self.send_http_response(
                            500,
                            vec![],
                            Some(
                                &format!("Error while ending HtmlRewriter: {}", e.to_string())
                                    .into_bytes(),
                            ),
                        );
                        return Action::Pause;
                    }
                    // Replace section of body to be modified with data emitted by the rewriter.
                    self.set_http_response_body(
                        0,
                        start_index + chunk_size,
                        self.output.borrow().as_slice(),
                    );
                    // Clear output after usage to avoid unnecessary memory growth.
                    self.output.borrow_mut().clear();
                    return Action::Continue;
                }
            } else {
                break;
            }
        }
        // Replace the entire chunk (0 to body_size) with the latest data emitted by the rewriter
        self.set_http_response_body(0, body_size, self.output.borrow().as_slice());
        // Clear output after usage to avoid unnecessary memory growth.
        self.output.borrow_mut().clear();
        return Action::Continue;
    }
}
// [END serviceextensions_plugin_enable_recaptcha]
