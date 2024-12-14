use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use std::rc::Rc;

proxy_wasm::main! { {
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext { secret: Rc::new("missing".to_string()) })
    });
} }

struct MyRootContext {
    secret: Rc<String>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        if let Some(config_bytes) = self.get_plugin_configuration() {
            self.secret = Rc::new(String::from_utf8(config_bytes).unwrap())
        }
        true
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            secret: self.secret.clone(), // shallow copy, ref count only
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    secret: Rc<String>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Use secret here...
        info!("secret: {}", self.secret);
        Action::Continue
    }
}
