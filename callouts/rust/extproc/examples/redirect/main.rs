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
//! # Redirect Example
//!
//! This module demonstrates how to create an Envoy external processor that
//! redirects all incoming HTTP requests to a specified URL.
//!
//! ## Overview
//!
//! The `RedirectProcessor` implements the `ExtProcessor` trait to intercept
//! HTTP requests and immediately respond with a redirect status code (301 Moved Permanently)
//! and a Location header pointing to the target URL.
//!
//! This example shows how to:
//! - Create an immediate response instead of modifying the request
//! - Set HTTP status codes
//! - Add HTTP headers for redirection
//!
//! ## Usage
//!
//! To run this example:
//!
//! ```bash
//! cargo run --example redirect
//! ```

use async_trait::async_trait;
use ext_proc::utils::mutations;
use ext_proc::{
    envoy::service::ext_proc::v3::{ProcessingRequest, ProcessingResponse},
    processor::{ExtProcessor, ProcessingError},
    server::{CalloutServer, Config},
};

/// `RedirectProcessor` returns a redirect response for all incoming HTTP requests.
///
/// This processor demonstrates how to create an immediate response with a redirect
/// status code (301 Moved Permanently) and a Location header pointing to the target URL.
/// It intercepts all requests at the request headers phase and returns a redirect
/// response without further processing.
#[derive(Clone)]
struct RedirectProcessor;

impl RedirectProcessor {
    /// Creates a new instance of `RedirectProcessor`.
    ///
    /// # Returns
    ///
    /// A new `RedirectProcessor` instance.
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for RedirectProcessor {
    /// Processes request headers and returns a redirect response.
    ///
    /// This method intercepts all incoming requests and immediately responds with
    /// a 301 Moved Permanently redirect to "http://service-extensions.com/redirect".
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing request headers (not used)
    ///
    /// # Returns
    ///
    /// A `ProcessingResponse` containing a redirect response with:
    /// - Status code 301 (Moved Permanently)
    /// - Location header with the target URL
    async fn process_request_headers(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(mutations::add_redirect_response(
            301,
            "http://service-extensions.com/redirect".to_string(),
            None,
        ))
    }

    /// Processes response headers.
    ///
    /// This implementation simply passes through response headers without modification,
    /// as the processor already responded with a redirect at the request headers phase.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing response headers
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the response headers to proceed unchanged.
    async fn process_response_headers(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    /// Processes request bodies.
    ///
    /// This implementation simply passes through request bodies without modification,
    /// as the processor already responded with a redirect at the request headers phase.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing the request body
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the request body to proceed unchanged.
    async fn process_request_body(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    /// Processes response bodies.
    ///
    /// This implementation simply passes through response bodies without modification,
    /// as the processor already responded with a redirect at the request headers phase.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing the response body
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the response body to proceed unchanged.
    async fn process_response_body(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }
}

/// Main entry point for the redirect example.
///
/// Sets up and starts the external processor server with the `RedirectProcessor`.
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
    let processor = RedirectProcessor::new();

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
    //! Test module for the `RedirectProcessor`.
    //!
    //! Contains comprehensive tests for the redirect functionality, including:
    //! - Verifying the redirect status code
    //! - Checking the Location header
    //! - Testing the structure of the immediate response
    //! - Ensuring other processor methods return default responses
    //! - Testing behavior with empty and different request types

    use super::*;
    use ext_proc::envoy::{
        config::core::v3::{HeaderMap, HeaderValue},
        service::ext_proc::v3::{
            processing_request::Request as ProcessingRequestVariant,
            processing_response::Response as ProcessingResponseVariant, HttpHeaders,
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

    /// Tests the basic redirect response functionality.
    ///
    /// This test verifies that:
    /// - The processor returns an immediate response
    /// - The status code is 301 (Moved Permanently)
    /// - The Location header contains the correct redirect URL
    #[tokio::test]
    async fn test_redirect_response() {
        let processor = RedirectProcessor::new();

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

        // Verify the response is an immediate response with redirect
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) =
            response.response
        {
            // Check status code
            assert_eq!(
                immediate_response.status.as_ref().unwrap().code,
                301,
                "Expected 301 status code"
            );

            // Check location header
            let headers = immediate_response.headers.as_ref().unwrap();
            let mut found_location = false;

            for header in &headers.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "Location" {
                        found_location = true;
                        assert_eq!(
                            String::from_utf8_lossy(&h.raw_value),
                            "http://service-extensions.com/redirect",
                            "Incorrect redirect URL"
                        );
                    }
                }
            }

            assert!(found_location, "Location header not found");
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    /// Tests that the redirect status code is correct.
    ///
    /// This test verifies that:
    /// - The status code in the immediate response is 301 (Moved Permanently)
    #[tokio::test]
    async fn test_redirect_status_code() {
        let processor = RedirectProcessor::new();

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

        // Verify the status code is 301 (Moved Permanently)
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) =
            response.response
        {
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301);
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    /// Tests that other processor methods return default responses.
    ///
    /// This test verifies that:
    /// - The response_headers, request_body, and response_body methods all return default responses
    /// - These methods don't modify the traffic in any way
    #[tokio::test]
    async fn test_other_processor_methods() {
        let processor = RedirectProcessor::new();
        let empty_request = ProcessingRequest::default();

        // Test response headers method
        let response = processor
            .process_response_headers(&empty_request)
            .await
            .expect("Failed to process response headers");
        assert_eq!(response, ProcessingResponse::default());

        // Test request body method
        let response = processor
            .process_request_body(&empty_request)
            .await
            .expect("Failed to process request body");
        assert_eq!(response, ProcessingResponse::default());

        // Test response body method
        let response = processor
            .process_response_body(&empty_request)
            .await
            .expect("Failed to process response body");
        assert_eq!(response, ProcessingResponse::default());
    }

    /// Tests handling of empty requests.
    ///
    /// This test verifies that:
    /// - Even with an empty request, the processor still returns a redirect response
    /// - The redirect contains the correct status code and Location header
    #[tokio::test]
    async fn test_empty_request() {
        let processor = RedirectProcessor::new();

        // Create an empty request
        let request = ProcessingRequest::default();

        // Even with an empty request, should still get a redirect
        let response = processor
            .process_request_headers(&request)
            .await
            .expect("Failed to process empty request");

        // Verify still get a redirect response
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) =
            response.response
        {
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301);

            // Check location header
            let headers = immediate_response.headers.as_ref().unwrap();
            let mut found_location = false;

            for header in &headers.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "Location" {
                        found_location = true;
                    }
                }
            }

            assert!(found_location, "Location header not found");
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    /// Tests behavior with different request types.
    ///
    /// This test verifies that:
    /// - The processor returns a redirect response for all request types
    /// - The redirect is consistent regardless of the input request type
    #[tokio::test]
    async fn test_different_request_types() {
        let processor = RedirectProcessor::new();

        // Test with different request types
        let request_types = vec![
            ProcessingRequestVariant::RequestHeaders(create_test_request_headers()),
            ProcessingRequestVariant::ResponseHeaders(create_test_request_headers()), // Using request headers as response headers for simplicity
            ProcessingRequestVariant::RequestBody(
                ext_proc::envoy::service::ext_proc::v3::HttpBody {
                    body: b"test body".to_vec(),
                    end_of_stream: true,
                },
            ),
            ProcessingRequestVariant::ResponseBody(
                ext_proc::envoy::service::ext_proc::v3::HttpBody {
                    body: b"test body".to_vec(),
                    end_of_stream: true,
                },
            ),
        ];

        for req_type in request_types {
            let request = ProcessingRequest {
                request: Some(req_type.clone()),
                ..Default::default()
            };

            // Only request headers should produce a redirect
            let response = processor
                .process_request_headers(&request)
                .await
                .expect("Failed to process request");

            // Verify redirect response
            if let Some(ProcessingResponseVariant::ImmediateResponse(_)) = response.response {
                // This is expected for request headers
            } else {
                panic!("Expected ImmediateResponse for request headers");
            }
        }
    }

    /// Tests the complete structure of the redirect response.
    ///
    /// This test verifies that:
    /// - The immediate response has the correct structure
    /// - All required fields are present and have the expected values
    /// - Optional fields have the expected default values
    #[tokio::test]
    async fn test_redirect_response_structure() {
        let processor = RedirectProcessor::new();

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

        // Verify the complete structure of the redirect response
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) =
            response.response
        {
            // Check status
            assert!(
                immediate_response.status.is_some(),
                "Status should be present"
            );
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301);

            // Check headers
            assert!(
                immediate_response.headers.is_some(),
                "Headers should be present"
            );

            // Check body (should be empty for redirects)
            assert!(
                immediate_response.body.is_empty(),
                "Body should be empty for redirects"
            );

            // Check details (should be empty)
            assert!(
                immediate_response.details.is_empty(),
                "Details should be empty"
            );

            // Check grpc_status (should be None for HTTP redirects)
            assert!(
                immediate_response.grpc_status.is_none(),
                "gRPC status should be None for HTTP redirects"
            );
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    /// Tests that the processor response matches the direct mutation result.
    ///
    /// This test verifies that:
    /// - The response from the processor matches the response created directly with the mutations helper
    /// - The processor is correctly using the mutations utility function
    #[tokio::test]
    async fn test_compare_with_direct_mutation() {
        let processor = RedirectProcessor::new();

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

        // Create the expected response directly using the mutations helper
        let expected_response = mutations::add_redirect_response(
            301,
            "http://service-extensions.com/redirect".to_string(),
            None,
        );

        // Compare the responses
        assert_eq!(
            response, expected_response,
            "Response should match the direct mutation result"
        );
    }
}
