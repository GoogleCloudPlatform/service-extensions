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

// [START serviceextensions_plugin_error_page_with_traceid]
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use regex::Regex;

// Custom HTML template for error pages
const ERROR_TEMPLATE: &str = r#"
<html>
<head>
  <title>Error {STATUS_CODE}</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; }
    .container { max-width: 800px; margin: 0 auto; }
    .trace-id { 
      background-color: #f5f5f5; 
      padding: 1rem; 
      font-family: monospace;
      word-break: break-all;
      margin-top: 2rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Error {STATUS_CODE}</h1>
    <p>We're sorry, something went wrong with your request.</p>
    
    <div class="trace-id">
      <strong>Trace ID:</strong> {TRACE_ID}
    </div>
    
    <p>Please provide this trace ID to support for assistance.</p>
  </div>
</body>
</html>
"#;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Debug);
    proxy_wasm::set_http_context(|_, _| -> Box<dyn HttpContext> { Box::new(ErrorPageWithTraceId::default()) });
}}

struct ErrorPageWithTraceId {
    trace_id: String,
}

impl Default for ErrorPageWithTraceId {
    fn default() -> Self {
        Self {
            trace_id: "not-available".to_string(),
        }
    }
}

impl Context for ErrorPageWithTraceId {}

impl HttpContext for ErrorPageWithTraceId {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        self.trace_id = self.extract_trace_id();
        log::debug!("Captured trace ID: {}", self.trace_id);
        Action::Continue
    }

    fn on_http_response_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        if let Some(status) = self.get_http_response_header(":status") {
            if let Ok(status_code) = status.parse::<u16>() {
                // Only handle error status codes (4xx and 5xx)
                if status_code >= 400 {
                    let error_page = ERROR_TEMPLATE
                        .replace("{STATUS_CODE}", &status)
                        .replace("{TRACE_ID}", &self.trace_id);

                    // Convert u16 to u32 for status code
                    self.send_http_response(
                        status_code as u32,
                        vec![("Content-Type", "text/html; charset=utf-8")],
                        Some(error_page.as_bytes()),
                    );
                    return Action::Pause;
                }
            }
        }
        Action::Continue
    }
}

impl ErrorPageWithTraceId {
    fn extract_trace_id(&self) -> String {
        // Try standard Google Cloud trace header first
        if let Some(trace_header) = self.get_http_request_header("x-cloud-trace-context") {
            // Format: TRACE_ID/SPAN_ID;o=TRACE_TRUE
            if let Some(slash_pos) = trace_header.find('/') {
                return trace_header[..slash_pos].to_string();
            }
            return trace_header;
        }

        // Try W3C Trace Context standard
        if let Some(w3c_trace) = self.get_http_request_header("traceparent") {
            // Format: version-trace_id-parent_id-flags
            let parts: Vec<&str> = w3c_trace.split('-').collect();
            let hex_regex = Regex::new(r"^[0-9a-fA-F]{32}$").unwrap();
            if parts.len() == 4 && hex_regex.is_match(parts[1]) {
                return parts[1].to_string(); // Return trace ID (second part)
            }
            return "invalid-trace-format".to_string();
        }

        "not-available".to_string()
    }
}
// [END serviceextensions_plugin_error_page_with_traceid]
