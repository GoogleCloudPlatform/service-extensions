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
#include "re2/re2.h"

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

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t) override {
    // Compile W3C trace context regex at startup
    w3c_trace_regex_ = std::make_unique<re2::RE2>(
        R"(^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$)", 
        re2::RE2::Quiet);
    if (!w3c_trace_regex_->ok()) {
      LOG_ERROR("Failed to compile W3C traceparent regex");
      return false;
    }
    return true;
  }

  std::unique_ptr<re2::RE2> w3c_trace_regex_;
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) 
      : Context(id, root), 
        root_(static_cast<MyRootContext*>(root)) {}

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

    // Try W3C Trace Context standard
    const auto w3c_trace = getRequestHeader("traceparent");
    if (w3c_trace && !w3c_trace->view().empty()) {
        const std::string trace_context = w3c_trace->toString();
        std::string trace_id;
        
        // Use precompiled regex to extract trace ID
        if (root_->w3c_trace_regex_ && 
            re2::RE2::FullMatch(trace_context, *root_->w3c_trace_regex_, &trace_id)) {
            return trace_id;
        }
        return "not-available";
    }

    return "not-available";
  }

  std::string status_code_;
  std::string trace_id_{"not-available"};  // Default value
  MyRootContext* root_;
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
// [END serviceextensions_plugin_error_page_with_traceid]
