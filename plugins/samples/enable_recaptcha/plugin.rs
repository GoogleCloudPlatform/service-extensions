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
// reCAPTCHA session or reCAPTCHA action. This is not a replacement for reading
// reCAPTCHA documentaion or following all user guide instructions. Please
// follow official reCAPTCHA documentation at
// https://developers.google.com/recaptcha.
use log::*;
use lol_html::html_content::ContentType;
use lol_html::*;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use serde::Deserialize;
use std::borrow::Cow;
use std::cell::RefCell;
use std::error::Error;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
      Box::new(MyRootContext {
          recaptcha_config: Rc::new(RefCell::new(RecaptchaConfig::default()))
      })
    });
}}

struct MyRootContext {
    recaptcha_config: Rc<RefCell<RecaptchaConfig>>,
}

#[derive(Deserialize, Debug, Default)]
struct RecaptchaConfig {
    recaptcha_key_type: String,
    recaptcha_key_value: String,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        if let Some(config) = self.get_plugin_configuration() {
            // Config file contains JSON formatted recaptcha config.
            // Use of .unwrap() is fine here, since failure in on_configure
            // should result in plugin crash.
            let config_lines = String::from_utf8(config).unwrap();
            let recaptcha_config: RecaptchaConfig = serde_json::from_str(&config_lines).unwrap();
            if recaptcha_config.recaptcha_key_type != "SESSION"
                && recaptcha_config.recaptcha_key_type != "ACTION"
            {
                error!(
                    "Invalid recaptcha_key_type found. on_response_body will be \"
                    treated as a no-op meaning body will not be parsed or \
                    modified by plugin. recaptcha_key_type={}",
                    recaptcha_config.recaptcha_key_type
                )
            }
            self.recaptcha_config = Rc::new(RefCell::new(recaptcha_config));
        }
        return true;
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext::new(self.recaptcha_config.clone())))
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
}

impl<'a> MyHttpContext<'a> {
    pub fn new(config: Rc<RefCell<RecaptchaConfig>>) -> MyHttpContext<'a> {
        let output = Rc::new(RefCell::new(Vec::new()));
        let completed_script_injection = Rc::new(RefCell::new(false));
        let recaptcha_config = config;
        let element_content_handler = Self::create_element_content_handler(
            recaptcha_config.clone(),
            completed_script_injection.clone(),
        );

        MyHttpContext {
            output: output.clone(),
            completed_script_injection: completed_script_injection.clone(),
            rewriter: Some(HtmlRewriter::new(
                Settings {
                    element_content_handlers: element_content_handler,
                    ..Settings::new()
                },
                MyOutputSink {
                    output_sink: output,
                },
            )),
        }
    }

    fn create_element_content_handler(
        recaptcha_config: Rc<RefCell<RecaptchaConfig>>,
        completed_script_injection: Rc<RefCell<bool>>,
    ) -> Vec<(Cow<'a, Selector>, ElementContentHandlers<'a>)> {
        let key_type = (*recaptcha_config.borrow()).recaptcha_key_type.clone();
        let content_handler = match (*recaptcha_config.borrow()).recaptcha_key_type.as_str() {
            "SESSION" => {
                let key_value = (*recaptcha_config.borrow()).recaptcha_key_value.clone();
                vec![element!("head", move |el| {
                    el.prepend(
                            format!("\n<script src=\"https://www.google.com/recaptcha/enterprise.js?render=&waf={}\" async defer></script>\n",
                            key_value).as_str(),
                            ContentType::Html,
                            );
                    *completed_script_injection.borrow_mut() = true;
                    Ok(())
                })]
            }
            "ACTION" => {
                let key_value = (*recaptcha_config.borrow()).recaptcha_key_value.clone();
                vec![element!("head", move |el| {
                    el.prepend(
                            format!("\n<script src=\"https://www.google.com/recaptcha/enterprise.js?render={}\"></script>\n",
                            key_value).as_str(),
                            ContentType::Html,
                            );
                    *completed_script_injection.borrow_mut() = true;
                    Ok(())
                })]
            }
            _ => {
                // Setting completed_script_injection to true to indicate no parsing/modification
                // of body will occur.
                *completed_script_injection.borrow_mut() = true;
                // Element handler will never be used because body will not be parsed.
                Vec::new()
            }
        };
        return content_handler;
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
                    // Prefer logging errors instead of panicking to avoid plugin crashes.
                    error!("Error while writing to HtmlRewriter: {}", e.to_string());
                    *self.completed_script_injection.borrow_mut() = true;
                    return Action::Pause;
                }
                if *self.completed_script_injection.borrow() {
                    if let Err(e) = self.end_rewriter() {
                        error!("Error while ending HtmlRewriter: {}", e.to_string());
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
