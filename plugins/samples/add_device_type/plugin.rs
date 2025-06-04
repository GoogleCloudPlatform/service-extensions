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

// Static keyword arrays defined once at compile time
fn is_bot(ua: &str) -> bool {
    static BOT_KEYWORDS: &[&str] = &[
        "bot", "crawler", "spider", "googlebot", 
        "bingbot", "slurp", "duckduckbot", "yandexbot", "baiduspider"
    ];
    contains_any(ua, BOT_KEYWORDS)
}

fn is_tablet(ua: &str) -> bool {
    static TABLET_KEYWORDS: &[&str] = &[
        "ipad", "tablet", "kindle", "tab", 
        "playbook", "nexus 7", "sm-t", "pad", "gt-p"
    ];
    
    static ANDROID_TABLET_INDICATORS: &[&str] = &["tablet", "tab", "pad"];
    
    if contains_any(ua, TABLET_KEYWORDS) {
        return true;
    }
    
    if ua.contains("android") {
        return contains_any(ua, ANDROID_TABLET_INDICATORS);
    }
    
    false
}

fn is_mobile(ua: &str) -> bool {
    static MOBILE_KEYWORDS: &[&str] = &[
        "mobile", "android", "iphone", "ipod", 
        "blackberry", "windows phone", "webos", "iemobile", "opera mini"
    ];
    contains_any(ua, MOBILE_KEYWORDS)
}

fn is_desktop(ua: &str) -> bool {
    static DESKTOP_KEYWORDS: &[&str] = &[
        "mozilla", "chrome", "safari", "firefox",
        "msie", "opera", "edge", "chromium", "vivaldi"
    ];
    contains_any(ua, DESKTOP_KEYWORDS)
}

fn contains_any(s: &str, subs: &[&str]) -> bool {
    subs.iter().any(|sub| s.contains(sub))
}
// [END serviceextensions_plugin_device_type]
