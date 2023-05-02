use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
 proxy_wasm::set_log_level(LogLevel::Trace);
 proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(HttpHeaders) });
}}

struct HttpHeaders;

impl HttpContext for HttpHeaders {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // TODO: add log statement
        self.add_http_request_header("example", "this is a test");
        Action::Continue
    }
    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        // TODO: add log statement
        self.add_http_response_header("response", "example response header");
        Action::Continue
    }
}

impl Context for HttpHeaders {}
