// Copyright 2023 Google LLC
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

use log::info;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        info!("root onCreate called");
        Box::new(MyRootContext)
    });
}}

struct MyRootContext;

impl Drop for MyRootContext {
    fn drop(&mut self) {
        info!("root onDelete called");
    }
}
impl Context for MyRootContext {
    fn on_done(&mut self) -> bool {
        info!("root onDone called");
        return true;
    }
}
impl RootContext for MyRootContext {
    fn on_vm_start(&mut self, _: usize) -> bool {
        info!("root onStart called");
        return true;
    }
    fn on_configure(&mut self, _: usize) -> bool {
        info!("root onConfigure called");
        return true;
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        info!("http onCreate called");
        Some(Box::new(MyHttpContext))
    }
    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext;

impl Drop for MyHttpContext {
    fn drop(&mut self) {
        info!("http onDelete called");
    }
}
impl Context for MyHttpContext {
    fn on_done(&mut self) -> bool {
        info!("http onDone called");
        return true;
    }
}
impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        info!("http onRequestHeaders called");
        return Action::Continue;
    }
    fn on_http_response_headers(&mut self, _: usize, _: bool) -> Action {
        info!("http onResponseHeaders called");
        return Action::Continue;
    }
}
