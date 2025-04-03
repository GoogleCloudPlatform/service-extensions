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
//! # Basic Processor Example
//!
//! This module demonstrates a comprehensive Envoy external processor that
//! modifies both HTTP headers and bodies in requests and responses.
//!
//! ## Overview
//!
//! The `BasicProcessor` implements the `ExtProcessor` trait to intercept and modify
//! HTTP traffic in four ways:
//!
//! 1. Adding custom headers to requests
//! 2. Adding custom headers to responses
//! 3. Replacing request body content
//! 4. Replacing response body content
//!
//! This example serves as a good starting point for understanding how to build
//! a complete external processor that handles all aspects of HTTP traffic.
//!
//! ## Usage
//!
//! To run this example:
//!
//! ```bash
//! cargo run --example basic
//! ```

use async_trait::async_trait;
use ext_proc::{
    envoy::service::ext_proc::v3::{
        processing_request::Request as ProcessingRequestVariant, ProcessingRequest,
        ProcessingResponse,
    },
    processor::{ExtProcessor, ProcessingError},
    server::{CalloutServer, Config},
    utils::mutations,
};

/// `BasicProcessor` demonstrates both header and body modifications for HTTP traffic.
///
/// This processor provides a complete example of HTTP traffic modification by:
/// - Adding a "header-request" header to all requests
/// - Adding a "header-response" header to all responses
/// - Replacing request bodies with "new-body-request"
/// - Replacing response bodies with "new-body-response"
#[derive(Clone)]
struct BasicProcessor;

impl BasicProcessor {
    /// Creates a new instance of `BasicProcessor`.
    ///
    /// # Returns
    ///
    /// A new `BasicProcessor` instance.
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for BasicProcessor {
    /// Processes request headers.
    ///
    /// Adds a custom "header-request" header with value "Value-request" to all requests.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing request headers
    ///
    /// # Returns
    ///
    /// A `ProcessingResponse` that adds the custom header to the request.
    async fn process_request_headers(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(mutations::add_header_mutation(
            vec![("header-request".to_string(), "Value-request".to_string())],
            vec![],
            false,
            true,
            None,
        ))
    }

    /// Processes response headers.
    ///
    /// Adds a custom "header-response" header with value "Value-response" to all responses.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing response headers
    ///
    /// # Returns
    ///
    /// A `ProcessingResponse` that adds the custom header to the response.
    async fn process_response_headers(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(mutations::add_header_mutation(
            vec![("header-response".to_string(), "Value-response".to_string())],
            vec![],
            false,
            false,
            None,
        ))
    }

    /// Processes request bodies.
    ///
    /// Replaces any request body with the string "new-body-request".
    ///
    /// # Arguments
    ///
    /// * `req` - The processing request containing the request body
    ///
    /// # Returns
    ///
    /// A `ProcessingResponse` that either:
    /// - Replaces the request body with "new-body-request" if a body is present
    /// - Passes through the request unchanged if no body is present
    async fn process_request_body(
        &self,
        req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        if let Some(ProcessingRequestVariant::RequestBody(_body)) = &req.request {
            return Ok(mutations::add_body_string_mutation(
                "new-body-request".to_string(),
                true,
                false,
            ));
        }

        // If no body, just pass through
        Ok(ProcessingResponse::default())
    }

    /// Processes response bodies.
    ///
    /// Replaces any response body with the string "new-body-response".
    ///
    /// # Arguments
    ///
    /// * `req` - The processing request containing the response body
    ///
    /// # Returns
    ///
    /// A `ProcessingResponse` that either:
    /// - Replaces the response body with "new-body-response" if a body is present
    /// - Passes through the response unchanged if no body is present
    async fn process_response_body(
        &self,
        req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        if let Some(ProcessingRequestVariant::ResponseBody(_body)) = &req.request {
            return Ok(mutations::add_body_string_mutation(
                "new-body-response".to_string(),
                false,
                false,
            ));
        }

        // If no body, just pass through
        Ok(ProcessingResponse::default())
    }
}

/// Main entry point for the basic example.
///
/// Sets up and starts the external processor server with the `BasicProcessor`.
///
/// # Returns
///
/// A Result indicating success or failure of the server startup.
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();

    // Using default config
    let config = Config::default();

    let server = CalloutServer::new(config);
    let processor = BasicProcessor::new();

    // Start all services
    let secure = server.spawn_grpc(processor.clone()).await;
    let plaintext = server.spawn_plaintext_grpc(processor.clone()).await;
    let health = server.spawn_health_check().await;

    // Wait for all services
    let _ = tokio::try_join!(secure, plaintext, health)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    //! Test module for the `BasicProcessor`.
    //!
    //! Contains comprehensive tests for both header and body modification functionality,
    //! including:
    //! - Adding headers to requests and responses
    //! - Replacing body content in requests and responses
    //! - End-to-end processing of a complete HTTP transaction

    use super::*;
    use ext_proc::envoy::{
        config::core::v3::{HeaderMap, HeaderValue},
        service::ext_proc::v3::{
            body_mutation::Mutation as BodyMutationType,
            processing_request::Request as ProcessingRequestVariant,
            processing_response::Response as ProcessingResponseVariant, HttpBody, HttpHeaders,
        },
    };

    /// Creates a test request with HTTP headers.
    ///
    /// # Returns
    ///
    /// An `HttpHeaders` object containing common request headers:
    /// - "host": "example.com"
    /// - "user-agent": "test-client"
    fn create_test_request_headers() -> HttpHeaders {
        HttpHeaders {
            headers: Some(HeaderMap {
                headers: vec![
                    HeaderValue {
                        key: "host".to_string(),
                        raw_value: b"example.com".to_vec(),
                        ..Default::default()
                    },
                    HeaderValue {
                        key: "user-agent".to_string(),
                        raw_value: b"test-client".to_vec(),
                        ..Default::default()
                    },
                ],
                ..Default::default()
            }),
            ..Default::default()
        }
    }

    /// Creates a test response with HTTP headers.
    ///
    /// # Returns
    ///
    /// An `HttpHeaders` object containing common response headers:
    /// - "content-type": "application/json"
    /// - "server": "test-server"
    fn create_test_response_headers() -> HttpHeaders {
        HttpHeaders {
            headers: Some(HeaderMap {
                headers: vec![
                    HeaderValue {
                        key: "content-type".to_string(),
                        raw_value: b"application/json".to_vec(),
                        ..Default::default()
                    },
                    HeaderValue {
                        key: "server".to_string(),
                        raw_value: b"test-server".to_vec(),
                        ..Default::default()
                    },
                ],
                ..Default::default()
            }),
            ..Default::default()
        }
    }

    /// Tests the `process_request_headers` method of `BasicProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly adds the "header-request" header to requests
    /// - The header has the expected value "Value-request"
    #[tokio::test]
    async fn test_process_request_headers() {
        let processor = BasicProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(
                create_test_request_headers(),
            )),
            ..Default::default()
        };

        let response = processor
            .process_request_headers(&request)
            .await
            .expect("Failed to process request headers");

        // Verify the response adds the expected header
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check if custom header is present
            let mut found_header = false;
            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "header-request" {
                        found_header = true;
                        assert_eq!(String::from_utf8_lossy(&h.raw_value), "Value-request");
                    }
                }
            }

            assert!(found_header, "Custom request header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests the `process_response_headers` method of `BasicProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly adds the "header-response" header to responses
    /// - The header has the expected value "Value-response"
    #[tokio::test]
    async fn test_process_response_headers() {
        let processor = BasicProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseHeaders(
                create_test_response_headers(),
            )),
            ..Default::default()
        };

        let response = processor
            .process_response_headers(&request)
            .await
            .expect("Failed to process response headers");

        // Verify the response adds the expected header
        if let Some(ProcessingResponseVariant::ResponseHeaders(headers_response)) =
            response.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check if custom header is present
            let mut found_header = false;
            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "header-response" {
                        found_header = true;
                        assert_eq!(String::from_utf8_lossy(&h.raw_value), "Value-response");
                    }
                }
            }

            assert!(found_header, "Custom response header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests the `process_request_body` method of `BasicProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly replaces request body content
    /// - The response contains the expected "new-body-request" string
    #[tokio::test]
    async fn test_process_request_body() {
        let processor = BasicProcessor::new();
        let body_content = b"test request body".to_vec();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestBody(HttpBody {
                body: body_content.clone(),
                end_of_stream: true,
            })),
            ..Default::default()
        };

        let response = processor
            .process_request_body(&request)
            .await
            .expect("Failed to process request body");

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::Body(new_body)) = &body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(new_body),
                    "new-body-request",
                    "Request body was not replaced with expected content"
                );
            } else {
                panic!("Expected Body mutation type");
            }
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests the `process_response_body` method of `BasicProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly replaces response body content
    /// - The response contains the expected "new-body-response" string
    #[tokio::test]
    async fn test_process_response_body() {
        let processor = BasicProcessor::new();
        let body_content = b"test response body".to_vec();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseBody(HttpBody {
                body: body_content.clone(),
                end_of_stream: true,
            })),
            ..Default::default()
        };

        let response = processor
            .process_response_body(&request)
            .await
            .expect("Failed to process response body");

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::Body(new_body)) = &body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(new_body),
                    "new-body-response",
                    "Response body was not replaced with expected content"
                );
            } else {
                panic!("Expected Body mutation type");
            }
        } else {
            panic!("Expected ResponseBody response");
        }
    }

    /// Tests the complete end-to-end processing flow of the `BasicProcessor`.
    ///
    /// This test verifies that:
    /// - All four processing methods work correctly in sequence
    /// - Request headers are modified as expected
    /// - Request body is replaced as expected
    /// - Response headers are modified as expected
    /// - Response body is replaced as expected
    ///
    /// This simulates a complete HTTP transaction through the processor.
    #[tokio::test]
    async fn test_end_to_end_processing() {
        let processor = BasicProcessor::new();

        // 1. Process request headers
        let req_headers = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(
                create_test_request_headers(),
            )),
            ..Default::default()
        };

        let resp_headers = processor
            .process_request_headers(&req_headers)
            .await
            .unwrap();

        // 2. Process request body
        let req_body = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestBody(HttpBody {
                body: b"original request body".to_vec(),
                end_of_stream: true,
            })),
            ..Default::default()
        };

        let resp_body = processor.process_request_body(&req_body).await.unwrap();

        // 3. Process response headers
        let resp_headers_req = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseHeaders(
                create_test_response_headers(),
            )),
            ..Default::default()
        };

        let resp_headers_resp = processor
            .process_response_headers(&resp_headers_req)
            .await
            .unwrap();

        // 4. Process response body
        let resp_body_req = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseBody(HttpBody {
                body: b"original response body".to_vec(),
                end_of_stream: true,
            })),
            ..Default::default()
        };

        let resp_body_resp = processor
            .process_response_body(&resp_body_req)
            .await
            .unwrap();

        // Verify all responses have the expected modifications

        // Request headers should have "header-request" added
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) =
            resp_headers.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();
            let mut found = false;
            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "header-request" {
                        found = true;
                        break;
                    }
                }
            }
            assert!(found, "Request header not added");
        } else {
            panic!("Unexpected response type for request headers");
        }

        // Request body should be replaced with "new-body-request"
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = resp_body.response {
            let body_mutation = body_response
                .response
                .as_ref()
                .unwrap()
                .body_mutation
                .as_ref()
                .unwrap();
            if let Some(BodyMutationType::Body(new_body)) = &body_mutation.mutation {
                assert_eq!(String::from_utf8_lossy(new_body), "new-body-request");
            } else {
                panic!("Expected Body mutation type for request body");
            }
        } else {
            panic!("Unexpected response type for request body");
        }

        // Response headers should have "header-response" added
        if let Some(ProcessingResponseVariant::ResponseHeaders(headers_response)) =
            resp_headers_resp.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();
            let mut found = false;
            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "header-response" {
                        found = true;
                        break;
                    }
                }
            }
            assert!(found, "Response header not added");
        } else {
            panic!("Unexpected response type for response headers");
        }

        // Response body should be replaced with "new-body-response"
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) =
            resp_body_resp.response
        {
            let body_mutation = body_response
                .response
                .as_ref()
                .unwrap()
                .body_mutation
                .as_ref()
                .unwrap();
            if let Some(BodyMutationType::Body(new_body)) = &body_mutation.mutation {
                assert_eq!(String::from_utf8_lossy(new_body), "new-body-response");
            } else {
                panic!("Expected Body mutation type for response body");
            }
        } else {
            panic!("Unexpected response type for response body");
        }
    }
}
