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
//! # Body Modification Example
//!
//! This module demonstrates how to create an Envoy external processor that
//! modifies HTTP request and response bodies.
//!
//! ## Overview
//!
//! The `AddBodyProcessor` implements the `ExtProcessor` trait to intercept and modify
//! HTTP bodies in both requests and responses. This example shows:
//!
//! - How to replace request bodies with new content
//! - How to replace response bodies with new content
//! - How to handle empty bodies
//! - How to use the mutations utility functions
//!
//! ## Usage
//!
//! To run this example:
//!
//! ```bash
//! cargo run --example add_body
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

/// `AddBodyProcessor` demonstrates body modifications for HTTP requests and responses.
///
/// This processor replaces request bodies with "new-body-request" and response bodies
/// with "new-body-response" when they are present. If no body is present, it passes
/// the request or response through unchanged.
#[derive(Clone)]
struct AddBodyProcessor;

impl AddBodyProcessor {
    /// Creates a new instance of `AddBodyProcessor`.
    ///
    /// # Returns
    ///
    /// A new `AddBodyProcessor` instance.
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for AddBodyProcessor {
    /// Processes request headers.
    ///
    /// This implementation simply passes through request headers without modification.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing request headers
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the request to proceed unchanged.
    async fn process_request_headers(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    /// Processes response headers.
    ///
    /// This implementation simply passes through response headers without modification.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing response headers
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the response to proceed unchanged.
    async fn process_response_headers(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
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

/// Main entry point for the add_body example.
///
/// Sets up and starts the external processor server with the `AddBodyProcessor`.
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
    let processor = AddBodyProcessor::new();

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
    //! Test module for the `AddBodyProcessor`.
    //!
    //! Contains comprehensive tests for body modification functionality,
    //! including:
    //! - Basic request and response body replacement
    //! - Empty body handling
    //! - Clear body mutations
    //! - Route cache clearing
    //! - Large body handling
    //! - Streaming body handling
    //! - Custom processor implementations

    use super::*;
    use ext_proc::envoy::service::ext_proc::v3::{
        body_mutation::Mutation as BodyMutationType,
        processing_request::Request as ProcessingRequestVariant,
        processing_response::Response as ProcessingResponseVariant, HttpBody,
    };

    /// Creates a test request with a request body.
    ///
    /// # Arguments
    ///
    /// * `content` - The body content as bytes
    /// * `end_of_stream` - Whether this is the end of the stream
    ///
    /// # Returns
    ///
    /// A `ProcessingRequest` containing the specified request body
    fn create_test_request_body(content: &[u8], end_of_stream: bool) -> ProcessingRequest {
        ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestBody(HttpBody {
                body: content.to_vec(),
                end_of_stream,
            })),
            ..Default::default()
        }
    }

    /// Creates a test request with a response body.
    ///
    /// # Arguments
    ///
    /// * `content` - The body content as bytes
    /// * `end_of_stream` - Whether this is the end of the stream
    ///
    /// # Returns
    ///
    /// A `ProcessingRequest` containing the specified response body
    fn create_test_response_body(content: &[u8], end_of_stream: bool) -> ProcessingRequest {
        ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseBody(HttpBody {
                body: content.to_vec(),
                end_of_stream,
            })),
            ..Default::default()
        }
    }
    /// Tests the `process_request_body` method of `AddBodyProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly replaces request body content
    /// - The response contains the expected "new-body-request" string
    /// - The clear_route_cache flag is set to false
    #[tokio::test]
    async fn test_process_request_body() {
        let processor = AddBodyProcessor::new();
        let body_content = b"test request body";

        let request = create_test_request_body(body_content, true);

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

            // Verify clear_route_cache is false
            assert!(
                !common_response.clear_route_cache,
                "clear_route_cache should be false"
            );
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests the `process_response_body` method of `AddBodyProcessor`.
    ///
    /// This test verifies that:
    /// - The processor correctly replaces response body content
    /// - The response contains the expected "new-body-response" string
    /// - The clear_route_cache flag is set to false
    #[tokio::test]
    async fn test_process_response_body() {
        let processor = AddBodyProcessor::new();
        let body_content = b"test response body";

        let request = create_test_response_body(body_content, true);

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

            // Verify clear_route_cache is false
            assert!(
                !common_response.clear_route_cache,
                "clear_route_cache should be false"
            );
        } else {
            panic!("Expected ResponseBody response");
        }
    }

    /// Tests handling of empty request bodies.
    ///
    /// This test verifies that:
    /// - When no request body is present, the processor returns a default response
    /// - The default response allows the request to pass through unchanged
    #[tokio::test]
    async fn test_empty_request_body() {
        let processor = AddBodyProcessor::new();

        // Create a request with no body
        let request = ProcessingRequest::default();

        let response = processor
            .process_request_body(&request)
            .await
            .expect("Failed to process empty request body");

        // For empty body, expect a default response (pass-through)
        assert_eq!(
            response,
            ProcessingResponse::default(),
            "Empty body should result in default response"
        );
    }

    /// Tests handling of empty response bodies.
    ///
    /// This test verifies that:
    /// - When no response body is present, the processor returns a default response
    /// - The default response allows the response to pass through unchanged
    #[tokio::test]
    async fn test_empty_response_body() {
        let processor = AddBodyProcessor::new();

        // Create a request with no body
        let request = ProcessingRequest::default();

        let response = processor
            .process_response_body(&request)
            .await
            .expect("Failed to process empty response body");

        // For empty body, expect a default response (pass-through)
        assert_eq!(
            response,
            ProcessingResponse::default(),
            "Empty body should result in default response"
        );
    }

    /// Tests the clear body mutation for request bodies.
    ///
    /// This test verifies that:
    /// - The `add_body_clear_mutation` function correctly creates a ClearBody mutation
    /// - The mutation is properly set to clear the request body
    /// - The clear_route_cache flag is set to false
    #[tokio::test]
    async fn test_clear_request_body() {
        // Test the clear body mutation directly
        let response = mutations::add_body_clear_mutation(true, false);

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear, "ClearBody should be true");
            } else {
                panic!("Expected ClearBody mutation type");
            }

            // Verify clear_route_cache is false
            assert!(
                !common_response.clear_route_cache,
                "clear_route_cache should be false"
            );
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests the clear body mutation for response bodies.
    ///
    /// This test verifies that:
    /// - The `add_body_clear_mutation` function correctly creates a ClearBody mutation
    /// - The mutation is properly set to clear the response body
    /// - The clear_route_cache flag is set to false
    #[tokio::test]
    async fn test_clear_response_body() {
        // Test the clear body mutation directly
        let response = mutations::add_body_clear_mutation(false, false);

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear, "ClearBody should be true");
            } else {
                panic!("Expected ClearBody mutation type");
            }

            // Verify clear_route_cache is false
            assert!(
                !common_response.clear_route_cache,
                "clear_route_cache should be false"
            );
        } else {
            panic!("Expected ResponseBody response");
        }
    }

    /// Tests body mutation with route cache clearing.
    ///
    /// This test verifies that:
    /// - When the clear_route_cache flag is set to true, it's properly included in the response
    /// - The body mutation still functions correctly with route cache clearing enabled
    #[tokio::test]
    async fn test_body_with_route_cache_clearing() {
        // Test body mutation with route cache clearing
        let response = mutations::add_body_string_mutation("test-body".to_string(), true, true);

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();

            // Verify clear_route_cache is true
            assert!(
                common_response.clear_route_cache,
                "clear_route_cache should be true"
            );
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests handling of large body replacements.
    ///
    /// This test verifies that:
    /// - The processor can handle large request bodies (10KB in this test)
    /// - The large body is correctly replaced with the expected content
    #[tokio::test]
    async fn test_large_body_replacement() {
        let processor = AddBodyProcessor::new();

        // Create a large body
        let large_body = vec![b'X'; 10000];
        let request = create_test_request_body(&large_body, true);

        let response = processor
            .process_request_body(&request)
            .await
            .expect("Failed to process large request body");

        // Verify the response replaces the large body
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::Body(new_body)) = &body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(new_body),
                    "new-body-request",
                    "Large request body was not replaced with expected content"
                );
            } else {
                panic!("Expected Body mutation type");
            }
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests handling of streaming bodies.
    ///
    /// This test verifies that:
    /// - The processor correctly handles bodies where end_of_stream is false
    /// - The streaming body is replaced with the expected content
    #[tokio::test]
    async fn test_streaming_body() {
        let processor = AddBodyProcessor::new();

        // Create a body with end_of_stream set to false (simulating streaming)
        let request = create_test_request_body(b"streaming chunk", false);

        let response = processor
            .process_request_body(&request)
            .await
            .expect("Failed to process streaming request body");

        // Verify the response still replaces the body
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::Body(new_body)) = &body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(new_body),
                    "new-body-request",
                    "Streaming request body was not replaced with expected content"
                );
            } else {
                panic!("Expected Body mutation type");
            }
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests a custom processor with different mutation types.
    ///
    /// This test verifies that:
    /// - A custom processor can use different mutation types for requests and responses
    /// - Request bodies can be cleared while response bodies are replaced
    /// - Route cache clearing can be selectively applied
    #[tokio::test]
    async fn test_modified_processor() {
        // Create a custom processor that uses clear body mutation for requests
        // and string replacement for responses
        struct CustomBodyProcessor;

        #[async_trait]
        impl ExtProcessor for CustomBodyProcessor {
            async fn process_request_headers(
                &self,
                _req: &ProcessingRequest,
            ) -> Result<ProcessingResponse, ProcessingError> {
                Ok(ProcessingResponse::default())
            }

            async fn process_response_headers(
                &self,
                _req: &ProcessingRequest,
            ) -> Result<ProcessingResponse, ProcessingError> {
                Ok(ProcessingResponse::default())
            }

            async fn process_request_body(
                &self,
                req: &ProcessingRequest,
            ) -> Result<ProcessingResponse, ProcessingError> {
                if let Some(ProcessingRequestVariant::RequestBody(_)) = &req.request {
                    return Ok(mutations::add_body_clear_mutation(true, false));
                }
                Ok(ProcessingResponse::default())
            }

            async fn process_response_body(
                &self,
                req: &ProcessingRequest,
            ) -> Result<ProcessingResponse, ProcessingError> {
                if let Some(ProcessingRequestVariant::ResponseBody(_)) = &req.request {
                    return Ok(mutations::add_body_string_mutation(
                        "custom-response".to_string(),
                        false,
                        true,
                    ));
                }
                Ok(ProcessingResponse::default())
            }
        }

        let processor = CustomBodyProcessor;

        // Test request body processing (should clear the body)
        let request = create_test_request_body(b"test body", true);
        let response = processor
            .process_request_body(&request)
            .await
            .expect("Failed to process request body");

        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear, "Request body should be cleared");
            } else {
                panic!("Expected ClearBody mutation type for request");
            }
        } else {
            panic!("Expected RequestBody response");
        }

        // Test response body processing (should replace with custom string and clear route cache)
        let request = create_test_response_body(b"test body", true);
        let response = processor
            .process_response_body(&request)
            .await
            .expect("Failed to process response body");

        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            let common_response = body_response.response.as_ref().unwrap();
            let body_mutation = common_response.body_mutation.as_ref().unwrap();

            if let Some(BodyMutationType::Body(new_body)) = &body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(new_body),
                    "custom-response",
                    "Response body was not replaced with expected content"
                );
            } else {
                panic!("Expected Body mutation type for response");
            }

            // Verify clear_route_cache is true
            assert!(
                common_response.clear_route_cache,
                "clear_route_cache should be true for response"
            );
        } else {
            panic!("Expected ResponseBody response");
        }
    }
}
