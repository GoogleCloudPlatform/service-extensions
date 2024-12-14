use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! { {
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(MyHttpContext) });
} }

struct MyHttpContext;

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        info!("onRequestHeaders: hello from wasm");

        // Route extension example: host rewrite
        self.set_http_request_header(":host", Some("service-extensions.com"));
        self.set_http_request_header(":path", Some("/"));
        return Action::Continue;
    }

    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        info!("onResponseHeaders: hello from wasm");

        // Traffic extension example: add response header
        self.add_http_response_header("hello", "service-extensions");
        return Action::Continue;
    }
}
