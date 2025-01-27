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
    // Stores page as rewriter parses and modifies HTML.
    // Only stores completed sections(e.g., when rewriter parses "<di", output
    // will be empty until the next chunk comes in. If the next chunk was
    // "v> <h1>foo</h", the output will contain "<div><h1>foo" ).
    output: Rc<RefCell<Vec<u8>>>,
    // HTML rewriter
    rewriter: Option<HtmlRewriter<'a, Box<dyn FnMut(&[u8])>>>,
    // True when plugin has finished its objective.
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
                    element_content_handlers: vec![element!("a[href]", move |el| {
                        let href = el.get_attribute("href").unwrap();
                        let modified_href = href.replace("foo", "bar");
                        if modified_href != href {
                            el.set_attribute("href", &modified_href).unwrap();
                            // Plugin has completed the planned domain rewrite.
                            *completed.borrow_mut() = true;
                        }

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
            // Return immediately if plugin is "done" to avoid unnecessary work and resource usage.
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
