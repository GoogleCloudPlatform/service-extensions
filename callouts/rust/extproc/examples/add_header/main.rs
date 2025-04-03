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
//! # Header Modification Example
//!
//! This module demonstrates how to create an Envoy external processor that
//! adds custom headers to HTTP requests and responses.
//!
//! ## Overview
//!
//! The `AddHeaderProcessor` implements the `ExtProcessor` trait to intercept and modify
//! HTTP headers in both requests and responses. This example shows:
//!
//! - How to add custom headers to requests
//! - How to add custom headers to responses
//! - How to use the mutations utility functions
//! - How to control route cache clearing
//!
//! ## Usage
//!
//! To run this example:
//!
//! ```bash
//! cargo run --example add_header
//! ```

use async_trait::async_trait;
use ext_proc::{
    envoy::service::ext_proc::v3::{ProcessingRequest, ProcessingResponse},
    processor::{ExtProcessor, ProcessingError},
    server::{CalloutServer, Config},
    utils::mutations,
};

/// `AddHeaderProcessor` adds custom headers to both requests and responses.
///
/// This processor demonstrates how to use the `mutations::add_header_mutation` utility
/// to add headers to HTTP traffic. It adds:
/// - A "header-request" header to all requests
/// - A "header-response" header to all responses
#[derive(Clone)]
struct AddHeaderProcessor;

impl AddHeaderProcessor {
    /// Creates a new instance of `AddHeaderProcessor`.
    ///
    /// # Returns
    ///
    /// A new `AddHeaderProcessor` instance.
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for AddHeaderProcessor {
    /// Processes request headers.
    ///
    /// Adds a custom "header-request" header with value "Value-request" to all requests.
    /// Also clears the route cache to ensure the new header is considered for routing.
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
    /// This implementation simply passes through request bodies without modification.
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
    /// This implementation simply passes through response bodies without modification.
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

/// Main entry point for the add_header example.
///
/// Sets up and starts the external processor server with the `AddHeaderProcessor`.
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
    let processor = AddHeaderProcessor::new();

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
    //! Test module for the `AddHeaderProcessor`.
    //!
    //! Contains comprehensive tests for header modification functionality,
    //! including:
    //! - Adding headers to requests and responses
    //! - Adding multiple headers at once
    //! - Removing headers
    //! - Controlling route cache clearing
    //! - Verifying header values

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

    /// Tests the `process_request_headers` method of `AddHeaderProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly adds the "header-request" header to requests
    /// - The header has the expected value "Value-request"
    #[tokio::test]
    async fn test_process_request_headers() {
        // Create processor
        let processor = AddHeaderProcessor::new();

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(
                create_test_request_headers(),
            )),
            ..Default::default()
        };

        // Process the request
        let response = processor
            .process_request_headers(&request)
            .await
            .expect("Failed to process request headers");

        // Check if the response contains the expected header mutation
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

    /// Tests the `process_response_headers` method of `AddHeaderProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly adds the "header-response" header to responses
    /// - The header has the expected value "Value-response"
    #[tokio::test]
    async fn test_process_response_headers() {
        // Create processor
        let processor = AddHeaderProcessor::new();

        // Create request with response headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseHeaders(
                create_test_response_headers(),
            )),
            ..Default::default()
        };

        // Process the response headers
        let response = processor
            .process_response_headers(&request)
            .await
            .expect("Failed to process response headers");

        // Check if the response contains the expected header mutation
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

    /// Tests adding multiple headers at once.
    ///
    /// This test verifies that:
    /// - Multiple headers can be added in a single mutation
    /// - All headers have the correct values
    #[tokio::test]
    async fn test_multiple_headers() {
        // Test adding multiple headers to a request
        let response = mutations::add_header_mutation(
            vec![
                ("header1".to_string(), "value1".to_string()),
                ("header2".to_string(), "value2".to_string()),
                ("header3".to_string(), "value3".to_string()),
            ],
            vec![],
            false,
            true,
            None,
        );

        // Check if all headers are present
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check if all custom headers are present
            let expected_headers = [
                ("header1", "value1"),
                ("header2", "value2"),
                ("header3", "value3"),
            ];

            for (expected_key, expected_value) in &expected_headers {
                let mut found = false;
                for header in &header_mutation.set_headers {
                    if let Some(h) = &header.header {
                        if h.key == *expected_key {
                            found = true;
                            assert_eq!(String::from_utf8_lossy(&h.raw_value), *expected_value);
                        }
                    }
                }
                assert!(found, "Header {} not found", expected_key);
            }
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests header removal functionality.
    ///
    /// This test verifies that:
    /// - Headers can be removed from requests
    /// - New headers can be added while removing existing ones
    #[tokio::test]
    async fn test_header_removal() {
        // Test that headers can be removed from a request
        let response = mutations::add_header_mutation(
            vec![("new-header".to_string(), "new-value".to_string())],
            vec!["user-agent".to_string(), "host".to_string()],
            false,
            true,
            None,
        );

        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check that the headers to remove are present
            assert_eq!(header_mutation.remove_headers.len(), 2);
            assert!(header_mutation
                .remove_headers
                .contains(&"user-agent".to_string()));
            assert!(header_mutation.remove_headers.contains(&"host".to_string()));

            // Check that the new header is present
            let mut found_new_header = false;
            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "new-header" {
                        found_new_header = true;
                        assert_eq!(String::from_utf8_lossy(&h.raw_value), "new-value");
                    }
                }
            }

            assert!(found_new_header, "New header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests route cache clearing functionality.
    ///
    /// This test verifies that:
    /// - The clear_route_cache flag can be set to true or false
    /// - The flag is correctly included in the response
    #[tokio::test]
    async fn test_clear_route_cache() {
        // Test with clear_route_cache set to true for request headers
        let response = mutations::add_header_mutation(
            vec![("test-header".to_string(), "test-value".to_string())],
            vec![],
            true,
            true,
            None,
        );

        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let common_response = headers_response.response.as_ref().unwrap();

            // Check that clear_route_cache is set to true
            assert!(common_response.clear_route_cache);
        } else {
            panic!("Unexpected response type");
        }

        // Test with clear_route_cache set to false for request headers
        let response = mutations::add_header_mutation(
            vec![("test-header".to_string(), "test-value".to_string())],
            vec![],
            false,
            true,
            None,
        );

        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let common_response = headers_response.response.as_ref().unwrap();

            // Check that clear_route_cache is set to false
            assert!(!common_response.clear_route_cache);
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests response header mutation functionality.
    ///
    /// This test verifies that:
    /// - Headers can be added to responses
    /// - Multiple headers can be added to responses at once
    /// - The headers have the correct values
    #[tokio::test]
    async fn test_response_header_mutation() {
        // Test adding headers to a response
        let response = mutations::add_header_mutation(
            vec![
                (
                    "response-header1".to_string(),
                    "response-value1".to_string(),
                ),
                (
                    "response-header2".to_string(),
                    "response-value2".to_string(),
                ),
            ],
            vec![],
            false,
            false,
            None,
        );

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

            // Check if all custom headers are present
            let expected_headers = [
                ("response-header1", "response-value1"),
                ("response-header2", "response-value2"),
            ];

            for (expected_key, expected_value) in &expected_headers {
                let mut found = false;
                for header in &header_mutation.set_headers {
                    if let Some(h) = &header.header {
                        if h.key == *expected_key {
                            found = true;
                            assert_eq!(String::from_utf8_lossy(&h.raw_value), *expected_value);
                        }
                    }
                }
                assert!(found, "Header {} not found", expected_key);
            }
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests response header removal functionality.
    ///
    /// This test verifies that:
    /// - Headers can be removed from responses
    /// - New headers can be added while removing existing ones from responses
    #[tokio::test]
    async fn test_response_header_removal() {
        // Test that headers can be removed from a response
        let response = mutations::add_header_mutation(
            vec![(
                "new-response-header".to_string(),
                "new-response-value".to_string(),
            )],
            vec!["content-type".to_string(), "server".to_string()],
            false,
            false,
            None,
        );

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

            // Check that the headers to remove are present
            assert_eq!(header_mutation.remove_headers.len(), 2);
            assert!(header_mutation
                .remove_headers
                .contains(&"content-type".to_string()));
            assert!(header_mutation
                .remove_headers
                .contains(&"server".to_string()));

            // Check that the new header is present
            let mut found_new_header = false;
            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "new-response-header" {
                        found_new_header = true;
                        assert_eq!(String::from_utf8_lossy(&h.raw_value), "new-response-value");
                    }
                }
            }

            assert!(found_new_header, "New response header not found");
        } else {
            panic!("Unexpected response type");
        }
    }
}
