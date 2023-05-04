use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(HttpHeaders) });
}}

struct HttpHeaders;

impl Context for HttpHeaders {}

impl HttpContext for HttpHeaders {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Always be a friendly proxy.
        self.add_http_request_header("Message", "hello");
        return Action::Continue;
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        // Conditionally add to a header value.
        let msg = self.get_http_response_header("Message");
        if msg.unwrap_or_default() == "foo" {
            self.add_http_response_header("Message", "bar");
        }
        return Action::Continue;
    }
}
