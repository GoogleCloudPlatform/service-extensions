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

// [START serviceextensions_plugin_mcp_translation]
use proxy_wasm::traits::{Context, HttpContext, RootContext};
use proxy_wasm::types::{Action, ContextType, LogLevel};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use chrono::Utc;
use uuid::Uuid;

// --- Configuration ---
const CONTEXT_HEADER_CONVERSATION_ID: &str = "x-conversation-id";
const CONTEXT_HEADER_USER_ID: &str = "x-user-id";
const CONTEXT_HEADER_TRACE_ID: &str = "x-trace-id";
const CONTENT_TYPE_JSON: &str = "application/json";
const HEADER_CONTENT_TYPE: &str = "content-type";

// --- MCP Structures ---
#[derive(Serialize, Deserialize, Debug, Clone)]
struct MCPContext {
    #[serde(skip_serializing_if = "Option::is_none")]
    conversation_id: Option<String>,
    message_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    user_id: Option<String>,
    timestamp: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    trace_id: Option<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(untagged)]
enum MCPParams {
    WithOriginalParams {
        context: MCPContext,
        #[serde(flatten)]
        original_params: Value,
    },
    ContextOnly {
        context: MCPContext,
    },
}

#[derive(Serialize, Deserialize, Debug)]
struct MCPRequest {
    jsonrpc: String,
    id: String,
    method: String,
    params: MCPParams,
}

#[derive(Serialize, Deserialize, Debug)]
struct MCPError {
    code: i64,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<Value>,
}

#[derive(Serialize, Deserialize, Debug)]
struct MCPResponse {
    jsonrpc: String,
    id: Value, // Can be string or number in response
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<MCPError>,
}

// Client-facing error structure when MCP tool returns an error
#[derive(Serialize, Deserialize, Debug)]
struct ClientFacingErrorDetail {
    code: String,
    message: String,
    details: Option<MCPError>, // Include the original MCP error
}

#[derive(Serialize, Deserialize, Debug)]
struct ClientFacingError {
    error: ClientFacingErrorDetail,
}

// Client-facing error structure for filter-internal errors (parsing, etc.)
#[derive(Serialize, Deserialize, Debug)]
struct FilterInternalErrorDetail {
    code: String, // e.g., MCP_PARSE_ERROR, MCP_TRANSFORM_ERROR_400
    message: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct FilterInternalError {
    error: FilterInternalErrorDetail,
}

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext {})
    });
}}

// --- Root Context ---
struct MyRootContext {}

impl Context for MyRootContext {}
impl RootContext for MyRootContext {
    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }

    fn create_http_context(&self, context_id: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            context_id,
            extracted_context: HashMap::new(),
            transform_request: false,
            transform_response: false,
        }))
    }
}

// --- HTTP Context ---
struct MyHttpContext {
    context_id: u32,
    extracted_context: HashMap<String, String>,
    transform_request: bool,
    transform_response: bool,
}

impl Context for MyHttpContext {
}

// HttpContext trait implementation
impl HttpContext for MyHttpContext {

    // --- Request Path ---

    fn on_http_request_headers(&mut self, _num_headers: usize, _eos: bool) -> Action {
        self.log(LogLevel::Trace, "on_http_request_headers called");
        self.transform_request = false;
        self.extracted_context.clear();
        let mut headers_to_remove: Vec<String> = Vec::new();

        if let Some(content_type) = self.get_http_request_header(HEADER_CONTENT_TYPE) {
            if content_type.to_lowercase().starts_with(CONTENT_TYPE_JSON) {
                self.log(LogLevel::Debug, "Request Content-Type is JSON. Preparing for transformation.");
                self.transform_request = true;

                for (name, value) in self.get_http_request_headers() {
                    let lower_name = name.to_lowercase();
                    if lower_name == CONTEXT_HEADER_CONVERSATION_ID ||
                        lower_name == CONTEXT_HEADER_USER_ID ||
                        lower_name == CONTEXT_HEADER_TRACE_ID {
                        self.log(LogLevel::Trace, &format!("Extracting context header: {} = {}", &name, &value));
                        self.extracted_context.insert(lower_name.clone(), value);
                        headers_to_remove.push(name);
                    }
                }

                for name in headers_to_remove {
                    self.log(LogLevel::Trace, &format!("Removing request header: {}", &name));
                    self.set_http_request_header(&name, None);
                }
            } else {
                self.log(LogLevel::Debug, &format!("Skipping non-JSON request (Content-Type: {})", content_type));
            }
        } else {
            self.log(LogLevel::Debug, "Skipping request transformation (no Content-Type header).");
        }

        Action::Continue
    }

    fn on_http_request_body(&mut self, body_size: usize, eos: bool) -> Action {
        if !eos {
            self.log(LogLevel::Trace, &format!("on_http_request_body called: size={}, streaming, waiting for full body.", body_size));
            return Action::Continue;
        }
        self.log(LogLevel::Trace, &format!("on_http_request_body called: size={}, eos={}", body_size, eos));


        if !self.transform_request {
            self.log(LogLevel::Trace, "Skipping request body processing (not flagged).");
            return Action::Continue;
        }

        if body_size == 0 {
            self.log(LogLevel::Warn, "Received empty request body for JSON content type.");
            let error_detail = FilterInternalErrorDetail {
                code: "MCP_EMPTY_REQUEST_BODY".to_string(),
                message: "Empty request body received for JSON content type".to_string(),
            };
            let error_response = FilterInternalError { error: error_detail };
            let error_body_string = serde_json::to_string(&error_response).unwrap_or_else(|_| "{\"error\":{\"code\":\"SERIALIZATION_FAILED\",\"message\":\"Failed to serialize error\"}}".to_string());
            let error_bytes = error_body_string.into_bytes();
            let content_length_str = error_bytes.len().to_string();

            self.send_http_response(
                400,
                vec![
                    (HEADER_CONTENT_TYPE, CONTENT_TYPE_JSON),
                    ("content-length", &content_length_str),
                    ("x-mcp-filter-error", "true")
                ],
                Some(&error_bytes)
            );
            return Action::Pause;
        }

        if let Some(body_bytes) = self.get_http_request_body(0, body_size) {
            match self.transform_to_mcp(&body_bytes) {
                Ok(mcp_body) => {
                    self.log(LogLevel::Info, "Successfully transformed request to MCP format.");
                    self.set_http_request_body(0, mcp_body.len(), &mcp_body);
                    Action::Continue
                }
                Err((status_code, error_code_str, error_message_str)) => {
                    self.log(LogLevel::Error, &format!("Failed to transform request to MCP: {}", error_message_str));
                    let error_detail = FilterInternalErrorDetail {
                        code: error_code_str,
                        message: error_message_str,
                    };
                    let error_response = FilterInternalError { error: error_detail };
                    let error_body_string = serde_json::to_string(&error_response).unwrap_or_else(|_| "{\"error\":{\"code\":\"SERIALIZATION_FAILED\",\"message\":\"Failed to serialize error\"}}".to_string());
                    let error_bytes = error_body_string.into_bytes();
                    let content_length_string = error_bytes.len().to_string();

                    self.send_http_response(
                        status_code,
                        vec![
                            (HEADER_CONTENT_TYPE, CONTENT_TYPE_JSON),
                            ("content-length", &content_length_string),
                            ("x-mcp-filter-error", "true")
                        ],
                        Some(&error_bytes)
                    );
                    return Action::Pause;
                }
            }
        } else {
            self.log(LogLevel::Error, &format!("Failed to get request body chunk (size: {})", body_size));
            let error_detail = FilterInternalErrorDetail {
                code: "MCP_INTERNAL_REQUEST_ERROR".to_string(),
                message: "Internal filter error: failed to retrieve request body".to_string(),
            };
            let error_response = FilterInternalError { error: error_detail };
            let error_body_string = serde_json::to_string(&error_response).unwrap_or_else(|_| "{\"error\":{\"code\":\"SERIALIZATION_FAILED\",\"message\":\"Failed to serialize error\"}}".to_string());
            let error_bytes = error_body_string.into_bytes();
            let content_length_str = error_bytes.len().to_string();
            self.send_http_response(
                500,
                vec![
                    (HEADER_CONTENT_TYPE, CONTENT_TYPE_JSON),
                    ("content-length", &content_length_str),
                    ("x-mcp-filter-error", "true")
                ],
                Some(&error_bytes)
            );
            Action::Pause
        }
    }

    // --- Response Path ---

    fn on_http_response_headers(&mut self, _num_headers: usize, _eos: bool) -> Action {
        self.log(LogLevel::Trace, "on_http_response_headers called");
        self.transform_response = false;

        if let Some(content_type) = self.get_http_response_header(HEADER_CONTENT_TYPE) {
            if content_type.to_lowercase().starts_with(CONTENT_TYPE_JSON) {
                self.log(LogLevel::Debug, "Response Content-Type is JSON. Preparing for transformation.");
                self.transform_response = true;
            } else {
                self.log(LogLevel::Debug, &format!("Skipping non-JSON response transformation (Content-Type: {})", content_type));
            }
        } else {
            self.log(LogLevel::Debug, "Skipping response transformation (no Content-Type header).");
        }
        Action::Continue
    }

    fn on_http_response_body(&mut self, body_size: usize, eos: bool) -> Action {
        if !eos {
            self.log(LogLevel::Trace, &format!("on_http_response_body called: size={}, streaming, waiting for full body.", body_size));
            return Action::Continue;
        }
        self.log(LogLevel::Trace, &format!("on_http_response_body called: size={}, eos={}", body_size, eos));

        if !self.transform_response {
            self.log(LogLevel::Trace, "Skipping response body processing (not flagged).");
            return Action::Continue;
        }

        if body_size == 0 {
            self.log(LogLevel::Debug, "Processing empty response body for JSON type.");
            let empty_json_bytes = b"{}"; // Client expects an empty JSON object
            self.set_http_response_body(0, empty_json_bytes.len(), empty_json_bytes);
            return Action::Continue;
        }

        if let Some(body_bytes) = self.get_http_response_body(0, body_size) {
            match self.transform_from_mcp(&body_bytes) {
                Ok(original_result_body_bytes) => {
                    self.log(LogLevel::Info, "Successfully transformed MCP response back to original format.");
                    self.set_http_response_body(0, original_result_body_bytes.len(), &original_result_body_bytes);
                    Action::Continue
                }
                Err((status_code, error_body_string)) => {
                    self.log(LogLevel::Warn, &format!(
                        "MCP transformation failed or tool returned error (status {}): {}",
                        status_code, error_body_string
                    ));
                    let error_bytes = error_body_string.into_bytes();
                    let content_length_str = error_bytes.len().to_string();
                    self.send_http_response(
                        status_code,
                        vec![
                            (HEADER_CONTENT_TYPE, CONTENT_TYPE_JSON),
                            ("content-length", &content_length_str),
                            ("x-mcp-filter-error", "true")
                        ],
                        Some(&error_bytes)
                    );
                    Action::Pause
                }
            }
        } else {
            self.log(LogLevel::Error, &format!("Failed to get response body chunk (size: {})", body_size));
            let error_detail = FilterInternalErrorDetail {
                code: "MCP_INTERNAL_RESPONSE_ERROR".to_string(),
                message: "Internal filter error: failed to retrieve response body".to_string(),
            };
            let error_response = FilterInternalError { error: error_detail };
            let error_body_string = serde_json::to_string(&error_response).unwrap_or_else(|_| "{\"error\":{\"code\":\"SERIALIZATION_FAILED\",\"message\":\"Failed to serialize error\"}}".to_string());
            let error_bytes = error_body_string.into_bytes();
            let content_length_str = error_bytes.len().to_string();
            self.send_http_response(
                500,
                vec![
                    (HEADER_CONTENT_TYPE, CONTENT_TYPE_JSON),
                    ("content-length", &content_length_str),
                    ("x-mcp-filter-error", "true")
                ],
                Some(&error_bytes)
            );
            Action::Pause
        }
    }
}

// --- Helper Functions & Optional Lifecycle Methods within MCPFilter ---
impl MyHttpContext {

    // Custom log function to add context ID prefix
    fn log(&self, level: LogLevel, message: &str) {
        let prefixed_message = format!("[MCPFilter ctx={}] {}", self.context_id, message);
        proxy_wasm::hostcalls::log(level, &prefixed_message).unwrap_or_else(|e| {
            eprintln!("[WASM Filter Log Error ctx={}] Failed host log: {:?}. Message: {}", self.context_id, e, message);
        });
    }

    // --- Transformation Logic ---

    fn transform_to_mcp(&self, body: &[u8]) -> Result<Vec<u8>, (u32, String, String)> { // status, error_code_string, error_message_string
        let original_request: Value = serde_json::from_slice(body)
            .map_err(|e| {
                self.log(LogLevel::Warn, &format!("Failed to parse request as JSON: {}", e));
                (400, "MCP_REQUEST_PARSE_ERROR".to_string(), format!("Failed to parse request as JSON: {}", e))
            })?;

        self.log(LogLevel::Trace, &format!("Parsed original request: {:?}", original_request));

        let method = original_request
            .get("method")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .ok_or_else(|| {
                self.log(LogLevel::Warn, "Missing or empty 'method' in original request");
                (400, "MCP_MISSING_METHOD".to_string(), "Missing or empty 'method' in original request".to_string())
            })?
            .to_string();

        let original_params = original_request.get("params").cloned().unwrap_or(Value::Null);

        let timestamp_str = Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
        let message_id = Uuid::new_v4().to_string();

        let context = MCPContext {
            conversation_id: self.extracted_context.get(CONTEXT_HEADER_CONVERSATION_ID).cloned(),
            message_id,
            user_id: self.extracted_context.get(CONTEXT_HEADER_USER_ID).cloned(),
            timestamp: timestamp_str,
            trace_id: self.extracted_context.get(CONTEXT_HEADER_TRACE_ID).cloned(),
        };

        let mcp_params = if original_params.is_null() || (original_params.is_object() && original_params.as_object().map_or(false, |o| o.is_empty())) {
            MCPParams::ContextOnly { context }
        } else {
            MCPParams::WithOriginalParams { context, original_params }
        };

        let mcp_request = MCPRequest {
            jsonrpc: "2.0".to_string(),
            id: Uuid::new_v4().to_string(), // New ID for MCP request
            method,
            params: mcp_params,
        };

        let mcp_json_bytes = serde_json::to_vec(&mcp_request)
            .map_err(|e| {
                self.log(LogLevel::Error, &format!("Failed to serialize MCP request: {}", e));
                (500, "MCP_INTERNAL_SERIALIZATION_ERROR".to_string(), format!("Internal filter error: Failed to serialize MCP request: {}", e))
            })?;

        self.log(LogLevel::Debug, &format!("Transformed MCP request body: {}", String::from_utf8_lossy(&mcp_json_bytes)));
        Ok(mcp_json_bytes)
    }

    fn transform_from_mcp(&self, body: &[u8]) -> Result<Vec<u8>, (u32, String)> { // status_code_hint, client_facing_error_body_string
        let mcp_response: MCPResponse = serde_json::from_slice(body)
            .map_err(|e| {
                self.log(LogLevel::Warn, &format!("Failed to parse MCP response JSON: {}", e));
                let err_detail = FilterInternalErrorDetail {
                    code: "MCP_RESPONSE_PARSE_ERROR".to_string(),
                    message: format!("Failed to parse MCP response JSON: {}", e),
                };
                let err_response = FilterInternalError { error: err_detail };
                (502, serde_json::to_string(&err_response).unwrap_or_default())
            })?;

        self.log(LogLevel::Trace, &format!("Parsed MCP response: {:?}", mcp_response));

        if let Some(error_payload) = mcp_response.error { // error_payload is MCPError
            self.log(LogLevel::Warn, &format!("MCP tool returned error: code={}, message={}", error_payload.code, error_payload.message));
            let client_error_detail = ClientFacingErrorDetail {
                code: "MCP_TOOL_ERROR".to_string(), // Generic code for "tool returned an error"
                message: "Error received from downstream tool.".to_string(), // Generic message
                details: Some(error_payload), // Embed the original MCPError
            };
            let client_error_response = ClientFacingError { error: client_error_detail };
            let client_error_string = serde_json::to_string(&client_error_response).unwrap_or_else(|e_ser|{
                self.log(LogLevel::Critical, &format!("Failed to serialize client-facing error JSON: {}", e_ser));
                json!({"error": {"code": "MCP_ERROR_SERIALIZATION_ERROR", "message": "Failed to serialize MCP error details"}}).to_string()
            });
            // Use 502 Bad Gateway when the upstream tool explicitly returns an error.
            // The actual HTTP status from the tool (if available in error_payload.code) might be used
            // or a mapping could be applied. For now, 502 is a safe bet for "bad response from upstream".
            return Err((502, client_error_string));
        }

        match mcp_response.result {
            Some(result_value) => {
                let result_bytes = serde_json::to_vec(&result_value)
                    .map_err(|e| {
                        self.log(LogLevel::Error, &format!("Failed to serialize extracted MCP result: {}", e));
                        let err_detail = FilterInternalErrorDetail {
                            code: "MCP_RESULT_SERIALIZATION_ERROR".to_string(),
                            message: format!("Internal filter error: Failed to serialize MCP result: {}", e),
                        };
                        let err_response = FilterInternalError { error: err_detail };
                        (500, serde_json::to_string(&err_response).unwrap_or_default())
                    })?;
                self.log(LogLevel::Debug, &format!("Extracted result for client: {}", String::from_utf8_lossy(&result_bytes)));
                Ok(result_bytes)
            }
            None => {
                self.log(LogLevel::Error, "Invalid MCP response: missing both 'result' and 'error' fields.");
                let err_detail = FilterInternalErrorDetail {
                    code: "MCP_INVALID_RESPONSE".to_string(),
                    message: "Invalid response from MCP tool: missing 'result' and 'error'".to_string(),
                };
                let err_response = FilterInternalError { error: err_detail };
                Err((502, serde_json::to_string(&err_response).unwrap_or_default()))
            }
        }
    }
}
// [END serviceextensions_plugin_mcp_translation]