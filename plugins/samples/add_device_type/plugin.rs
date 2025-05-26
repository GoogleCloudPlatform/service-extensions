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

// [START serviceextensions_plugin_device_type]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(DeviceTypeContext) });
}}

struct DeviceTypeContext;

impl Context for DeviceTypeContext {}

impl HttpContext for DeviceTypeContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        let user_agent = self.get_http_request_header("user-agent")
            .unwrap_or_default()
            .to_lowercase();

        let device_type = detect_device_type(&user_agent);
        self.set_http_request_header("x-device-type", Some(&device_type));

        Action::Continue
    }
}

fn detect_device_type(ua: &str) -> String {
    if is_bot(ua) {
        return "bot".to_string();
    }
    if is_tablet(ua) {
        return "tablet".to_string();
    }
    if is_mobile(ua) {
        return "phone".to_string();
    }
    if is_desktop(ua) {
        return "desktop".to_string();
    }
    "other".to_string()
}

fn is_bot(ua: &str) -> bool {
    let bot_keywords = [
        "bot", "crawler", "spider", "googlebot", 
        "bingbot", "slurp", "duckduckbot", "yandexbot", "baiduspider"
    ];
    contains_any(ua, &bot_keywords)
}

fn is_tablet(ua: &str) -> bool {
    let tablet_keywords = [
        "ipad", "tablet", "kindle", "tab", 
        "playbook", "nexus 7", "sm-t", "pad", "gt-p"
    ];
    
    if contains_any(ua, &tablet_keywords) {
        return true;
    }
    
    if ua.contains("android") {
        let android_tablet_indicators = ["tablet", "tab", "pad"];
        return contains_any(ua, &android_tablet_indicators);
    }
    
    false
}

fn is_mobile(ua: &str) -> bool {
    let mobile_keywords = [
        "mobile", "android", "iphone", "ipod", 
        "blackberry", "windows phone", "webos", "iemobile", "opera mini"
    ];
    contains_any(ua, &mobile_keywords)
}

fn is_desktop(ua: &str) -> bool {
    let desktop_keywords = [
        "mozilla", "chrome", "safari", "firefox",
        "msie", "opera", "edge", "chromium", "vivaldi"
    ];
    contains_any(ua, &desktop_keywords)
}

fn contains_any(s: &str, subs: &[&str]) -> bool {
    subs.iter().any(|sub| s.contains(sub))
}
// [END serviceextensions_plugin_device_type]