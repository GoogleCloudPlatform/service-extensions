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

// [START serviceextensions_regex_rewrite]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use regex::Regex;
use std::rc::Rc;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext { path_match: Rc::new(None) })
    });
}}

struct MyRootContext {
    path_match: Rc<Option<Regex>>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        // TODO remove this example of mutating an Rc
        //*Rc::get_mut(&mut self.path_match).unwrap() = Some(Regex::new(r"/foo-([^/]+)/").unwrap());
        self.path_match = Rc::new(Some(Regex::new(r"/foo-([^/]+)/").unwrap()));
        return true;
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            path_match: self.path_match.clone(), // shallow copy, ref count only
        }))
    }
    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

struct MyHttpContext {
    path_match: Rc<Option<Regex>>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        if let Some(path) = self.get_http_request_header(":path") {
            //let captures = self.path_match.captures(&path).unwrap();
            let re: &Regex = &self.path_match.as_ref().as_ref().unwrap();
            let edit = re.replace(&path, "/$1/");
            if path.len() != edit.len() {
                self.set_http_request_header(":path", Some(&edit));
            }
        }
        return Action::Continue;
    }
}
// [END serviceextensions_regex_rewrite]
