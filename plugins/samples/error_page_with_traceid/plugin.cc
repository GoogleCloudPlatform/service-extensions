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
#include "absl/strings/str_cat.h"
#include "absl/strings/str_replace.h"
#include "proxy_wasm_intrinsics.h"
#include <regex>

// Custom HTML template for error pages
constexpr std::string_view kErrorTemplate = R"(
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
)";

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Capture trace ID early from request headers
    trace_id_ = extractTraceId();
    LOG_DEBUG(absl::StrCat("Captured trace ID: ", trace_id_));
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers, 
                                        bool end_of_stream) override {
    const auto status_header = getResponseHeader(":status");
    if (!status_header) return FilterHeadersStatus::Continue;

    status_code_ = status_header->toString();
    int status_code;
    if (!absl::SimpleAtoi(status_code_, &status_code)) {
        status_code = 500; // Fallback to internal server error if conversion fails
    }

    // Only handle error status codes (4xx and 5xx)
    if (status_code < 400) return FilterHeadersStatus::Continue;

    // Generate custom error page
    std::string error_page = std::string(kErrorTemplate);
    error_page = absl::StrReplaceAll(error_page, {
        {"{STATUS_CODE}", status_code_},
        {"{TRACE_ID}", trace_id_}
    });
    
    // Send custom error page as local response
    sendLocalResponse(
      status_code,  // Preserve original status code
      "",           // No additional details
      error_page,   // HTML content
      {{"Content-Type", "text/html; charset=utf-8"}} // Headers
    );

    return FilterHeadersStatus::StopIteration;
  }

 private:
 std::string extractTraceId() {
  // Try standard Google Cloud trace header first
  const auto trace_header = getRequestHeader("x-cloud-trace-context");
  if (trace_header && !trace_header->view().empty()) {
      const std::string trace_context = trace_header->toString();
      
      // Format: TRACE_ID/SPAN_ID;o=TRACE_TRUE
      const size_t slash_pos = trace_context.find('/');
      if (slash_pos != std::string::npos) {
          return trace_context.substr(0, slash_pos);
      }
      return trace_context;
  }

  // Try W3C Trace Context standard with regex
  const auto w3c_trace = getRequestHeader("traceparent");
  if (w3c_trace && !w3c_trace->view().empty()) {
      const std::string trace_context = w3c_trace->toString();
      
      // Format: version-trace_id-parent_id-flags
      std::regex hex_regex(R"(^[0-9a-fA-F]{32}$)"); // Regex for hex digits
      std::vector<std::string> parts;
      size_t start = 0;
      size_t end = trace_context.find('-');

      while (end != std::string::npos) {
          parts.push_back(trace_context.substr(start, end - start));
          start = end + 1;
          end = trace_context.find('-', start);
      }
      
      // Add the last part
      if (start < trace_context.length()) {
          parts.push_back(trace_context.substr(start));
      }
      
      // W3C format: version-trace_id-parent_id-flags
      if (parts.size() == 4 && std::regex_match(parts[1], hex_regex)) {
          return parts[1]; // Return trace ID (second part)
      }
      
      return "invalid-trace-format";
  }

  return "not-available";
  }

  std::string status_code_;
  std::string trace_id_{"not-available"};  // Default value
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
// [END serviceextensions_plugin_error_page_with_traceid]
