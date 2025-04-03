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
//! # Mutations Utility Module
//!
//! This module provides utility functions for creating common mutations to HTTP requests and responses
//! in Envoy external processors. These functions simplify the creation of processing responses for
//! modifying headers, bodies, and generating immediate responses.
//!
//! ## Overview
//!
//! The mutations module includes functions for:
//!
//! - Adding and removing HTTP headers
//! - Replacing HTTP body content
//! - Clearing HTTP body content
//! - Creating immediate responses with custom status codes
//! - Creating redirect responses
//!
//! These utilities abstract away the complexity of constructing the correct Envoy protobuf message
//! structures, making it easier to implement common HTTP traffic modifications.

use crate::envoy::r#type::v3::HttpStatus;
use crate::envoy::service::ext_proc::v3::processing_response::Response;
use crate::envoy::service::ext_proc::v3::{
    body_mutation, processing_response, BodyMutation, BodyResponse, ImmediateResponse,
};
use crate::envoy::{
    config::core::v3::{HeaderValue, HeaderValueOption},
    service::ext_proc::v3::{
        processing_response::Response as ProcessingResponseType, CommonResponse, HeaderMutation,
        HeadersResponse, ProcessingResponse,
    },
};

/// Creates a processing response that adds and/or removes HTTP headers.
///
/// This function constructs a `ProcessingResponse` that modifies HTTP headers in either
/// requests or responses, depending on the `is_request` parameter.
///
/// # Arguments
///
/// * `headers_to_add` - A vector of (key, value) pairs representing headers to add or replace
/// * `headers_to_remove` - A vector of header names to remove
/// * `clear_route_cache` - Whether to clear Envoy's route cache after modifying headers
/// * `is_request` - If true, modifies request headers; if false, modifies response headers
/// * `append_action` - Optional append action for all headers (0=APPEND_NONE, 1=APPEND_IF_EXISTS_OR_ADD, 2=APPEND_IF_EXISTS)
///
/// # Returns
///
/// A `ProcessingResponse` that adds and/or removes the specified headers
#[allow(deprecated)]
pub fn add_header_mutation(
    headers_to_add: Vec<(String, String)>,
    headers_to_remove: Vec<String>,
    clear_route_cache: bool,
    is_request: bool,
    append_action: Option<i32>,
) -> ProcessingResponse {
    let header_mutation = HeaderMutation {
        set_headers: headers_to_add
            .into_iter()
            .map(|(key, value)| HeaderValueOption {
                header: Some(HeaderValue {
                    key: key.to_string(),
                    raw_value: value.as_bytes().to_vec(),
                    ..Default::default()
                }),
                append: None, // Keep for backwards compatibility
                append_action: append_action.unwrap_or(0), // Default to APPEND_NONE (0)
                keep_empty_value: false,
            })
            .collect(),
        remove_headers: headers_to_remove,
    };

    let common_response = CommonResponse {
        header_mutation: Some(header_mutation),
        clear_route_cache,
        ..Default::default()
    };

    let headers_response = HeadersResponse {
        response: Some(common_response),
    };

    // Choose the appropriate response type based on is_request
    let response = if is_request {
        ProcessingResponseType::RequestHeaders(headers_response)
    } else {
        ProcessingResponseType::ResponseHeaders(headers_response)
    };

    ProcessingResponse {
        response: Some(response),
        mode_override: None,
        dynamic_metadata: None,
        override_message_timeout: None,
    }
}

/// Creates a processing response that replaces the HTTP body with a string.
///
/// This function constructs a `ProcessingResponse` that replaces the body content
/// in either requests or responses, depending on the `is_request` parameter.
///
/// # Arguments
///
/// * `body` - The string to use as the new body content
/// * `is_request` - If true, modifies request body; if false, modifies response body
/// * `clear_route_cache` - Whether to clear Envoy's route cache after modifying the body
///
/// # Returns
///
/// A `ProcessingResponse` that replaces the body with the specified string
pub fn add_body_string_mutation(
    body: String,
    is_request: bool,
    clear_route_cache: bool,
) -> ProcessingResponse {
    let body_mutation = BodyMutation {
        mutation: Some(body_mutation::Mutation::Body(body.into_bytes())),
    };

    let common_response = CommonResponse {
        body_mutation: Some(body_mutation),
        clear_route_cache,
        ..Default::default()
    };

    let body_response = BodyResponse {
        response: Some(common_response),
    };

    let mut response = ProcessingResponse::default();
    if is_request {
        response.response = Some(processing_response::Response::RequestBody(body_response));
    } else {
        response.response = Some(processing_response::Response::ResponseBody(body_response));
    }
    response
}

/// Creates a processing response that clears the HTTP body.
///
/// This function constructs a `ProcessingResponse` that removes all body content
/// from either requests or responses, depending on the `is_request` parameter.
///
/// # Arguments
///
/// * `is_request` - If true, clears request body; if false, clears response body
/// * `clear_route_cache` - Whether to clear Envoy's route cache after clearing the body
///
/// # Returns
///
/// A `ProcessingResponse` that clears the body content
pub fn add_body_clear_mutation(is_request: bool, clear_route_cache: bool) -> ProcessingResponse {
    let body_mutation = BodyMutation {
        mutation: Some(body_mutation::Mutation::ClearBody(true)),
    };

    let common_response = CommonResponse {
        body_mutation: Some(body_mutation),
        clear_route_cache,
        ..Default::default()
    };

    let body_response = BodyResponse {
        response: Some(common_response),
    };

    let mut response = ProcessingResponse::default();
    if is_request {
        response.response = Some(processing_response::Response::RequestBody(body_response));
    } else {
        response.response = Some(processing_response::Response::ResponseBody(body_response));
    }
    response
}

/// Creates an immediate response with custom status code, headers, and body.
///
/// This function constructs a `ProcessingResponse` that immediately responds to a request
/// without further processing, allowing for custom status codes, headers, and body content.
///
/// # Arguments
///
/// * `status_code` - The HTTP status code for the response
/// * `headers` - A vector of (key, value) pairs representing headers to include
/// * `body` - Optional body content as bytes
/// * `append_action` - Optional append action for all headers (0=APPEND_NONE, 1=APPEND_IF_EXISTS_OR_ADD, 2=APPEND_IF_EXISTS)
///
/// # Returns
///
/// A `ProcessingResponse` containing an immediate response with the specified attributes
#[allow(deprecated)]
pub fn add_immediate_response(
    status_code: u32,
    headers: Vec<(String, String)>,
    body: Option<Vec<u8>>,
    append_action: Option<i32>,
) -> ProcessingResponse {
    let header_mutation = HeaderMutation {
        set_headers: headers
            .into_iter()
            .map(|(key, value)| HeaderValueOption {
                header: Some(HeaderValue {
                    key,
                    raw_value: value.into_bytes(),
                    ..Default::default()
                }),
                append: None, // Keep for backwards compatibility
                append_action: append_action.unwrap_or(0), // Default to APPEND_NONE (0)
                keep_empty_value: false,
            })
            .collect(),
        remove_headers: Vec::new(),
    };

    let immediate_response = ImmediateResponse {
        status: Some(HttpStatus {
            code: status_code as i32,
        }),
        headers: Some(header_mutation),
        body: body.unwrap_or_default(),
        grpc_status: None,
        details: String::new(),
    };

    ProcessingResponse {
        response: Some(Response::ImmediateResponse(immediate_response)),
        mode_override: None,
        dynamic_metadata: None,
        override_message_timeout: None,
    }
}

/// Creates a redirect response with the specified status code and location.
///
/// This function constructs a `ProcessingResponse` that redirects the client to a new URL.
/// It's a specialized version of `add_immediate_response` specifically for redirects.
///
/// # Arguments
///
/// * `status_code` - The HTTP redirect status code (e.g., 301, 302, 303, 307, 308)
/// * `location` - The URL to redirect to
/// * `append_action` - Optional append action for the Location header (0=APPEND_NONE, 1=APPEND_IF_EXISTS_OR_ADD, 2=APPEND_IF_EXISTS)
///
/// # Returns
///
/// A `ProcessingResponse` containing a redirect response
pub fn add_redirect_response(
    status_code: u32,
    location: String,
    append_action: Option<i32>,
) -> ProcessingResponse {
    add_immediate_response(
        status_code,
        vec![("Location".to_string(), location)],
        None,
        append_action,
    )
}

#[cfg(test)]
mod tests {
    //! Tests for the mutations utility functions.
    //!
    //! These tests verify that each mutation function correctly constructs
    //! the appropriate Envoy processing response with the expected structure
    //! and content.

    use super::*;
    use crate::envoy::service::ext_proc::v3::processing_response::Response as ProcessingResponseVariant;

    /// Tests adding headers to a request.
    ///
    /// Verifies that:
    /// - The correct response variant is created (RequestHeaders)
    /// - Headers are correctly added
    /// - Headers are correctly marked for removal
    /// - Route cache clearing is correctly set
    #[test]
    fn test_add_header_mutation_request() {
        // Test adding headers to a request
        let headers_to_add = vec![
            ("X-Test-Header".to_string(), "test-value".to_string()),
            ("X-Another-Header".to_string(), "another-value".to_string()),
        ];
        let headers_to_remove = vec!["X-Remove-Me".to_string()];

        let response = add_header_mutation(headers_to_add, headers_to_remove, true, true, None);

        // Verify request headers response
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            // Use as_ref() to borrow the contents instead of taking ownership
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check added headers
            assert_eq!(header_mutation.set_headers.len(), 2);
            assert_eq!(
                header_mutation.set_headers[0].header.as_ref().unwrap().key,
                "X-Test-Header"
            );
            assert_eq!(
                String::from_utf8_lossy(
                    &header_mutation.set_headers[0]
                        .header
                        .as_ref()
                        .unwrap()
                        .raw_value
                ),
                "test-value"
            );

            // Check removed headers
            assert_eq!(header_mutation.remove_headers.len(), 1);
            assert_eq!(header_mutation.remove_headers[0], "X-Remove-Me");

            // Check route cache clearing
            assert!(
                headers_response
                    .response
                    .as_ref()
                    .unwrap()
                    .clear_route_cache
            );
        } else {
            panic!("Expected RequestHeaders response");
        }
    }

    /// Tests adding headers to a response.
    ///
    /// Verifies that:
    /// - The correct response variant is created (ResponseHeaders)
    #[test]
    fn test_add_header_mutation_response() {
        // Test adding headers to a response
        let headers_to_add = vec![("X-Test-Header".to_string(), "test-value".to_string())];
        let headers_to_remove = vec![];

        let response = add_header_mutation(headers_to_add, headers_to_remove, false, false, None);

        // Verify response headers response
        if let Some(ProcessingResponseVariant::ResponseHeaders(_)) = response.response {
            // Test passed
        } else {
            panic!("Expected ResponseHeaders response");
        }
    }

    /// Tests replacing a request body with a string.
    ///
    /// Verifies that:
    /// - The correct response variant is created (RequestBody)
    /// - The body content is correctly set
    #[test]
    fn test_add_body_string_mutation_request() {
        let body = "Modified request body";
        let response = add_body_string_mutation(body.to_string(), true, false);

        // Verify request body response
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response
                .response
                .as_ref()
                .unwrap()
                .body_mutation
                .as_ref()
                .unwrap();

            if let Some(body_mutation::Mutation::Body(modified_body)) = &body_mutation.mutation {
                assert_eq!(String::from_utf8_lossy(modified_body), body);
            } else {
                panic!("Expected Body mutation");
            }
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests replacing a response body with a string.
    ///
    /// Verifies that:
    /// - The correct response variant is created (ResponseBody)
    /// - The body content is correctly set
    /// - Route cache clearing is correctly set
    #[test]
    fn test_add_body_string_mutation_response() {
        let body = "Modified response body";
        let response = add_body_string_mutation(body.to_string(), false, true);

        // Verify response body response
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response
                .response
                .as_ref()
                .unwrap()
                .body_mutation
                .as_ref()
                .unwrap();

            if let Some(body_mutation::Mutation::Body(modified_body)) = &body_mutation.mutation {
                assert_eq!(String::from_utf8_lossy(modified_body), body);
            } else {
                panic!("Expected Body mutation");
            }

            // Check route cache clearing
            assert!(body_response.response.as_ref().unwrap().clear_route_cache);
        } else {
            panic!("Expected ResponseBody response");
        }
    }

    /// Tests clearing a request body.
    ///
    /// Verifies that:
    /// - The correct response variant is created (RequestBody)
    /// - The ClearBody mutation is correctly set
    #[test]
    fn test_add_body_clear_mutation_request() {
        let response = add_body_clear_mutation(true, false);

        // Verify request body response with clear body
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response
                .response
                .as_ref()
                .unwrap()
                .body_mutation
                .as_ref()
                .unwrap();

            if let Some(body_mutation::Mutation::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear);
            } else {
                panic!("Expected ClearBody mutation");
            }
        } else {
            panic!("Expected RequestBody response");
        }
    }

    /// Tests clearing a response body.
    ///
    /// Verifies that:
    /// - The correct response variant is created (ResponseBody)
    /// - The ClearBody mutation is correctly set
    /// - Route cache clearing is correctly set
    #[test]
    fn test_add_body_clear_mutation_response() {
        let response = add_body_clear_mutation(false, true);

        // Verify response body response with clear body
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response
                .response
                .as_ref()
                .unwrap()
                .body_mutation
                .as_ref()
                .unwrap();

            if let Some(body_mutation::Mutation::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear);
            } else {
                panic!("Expected ClearBody mutation");
            }

            // Check route cache clearing
            assert!(body_response.response.as_ref().unwrap().clear_route_cache);
        } else {
            panic!("Expected ResponseBody response");
        }
    }

    /// Tests creating an immediate response.
    ///
    /// Verifies that:
    /// - The correct response variant is created (ImmediateResponse)
    /// - The status code is correctly set
    /// - Headers are correctly added
    /// - Body content is correctly set
    #[test]
    fn test_add_immediate_response() {
        let status_code = 403;
        let headers = vec![
            ("X-Test-Header".to_string(), "test-value".to_string()),
            ("Content-Type".to_string(), "text/plain".to_string()),
        ];
        let body = Some(b"Access denied".to_vec());

        let response = add_immediate_response(status_code, headers, body, None);

        // Verify immediate response
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) =
            response.response
        {
            // Check status code
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 403);

            // Check headers
            let header_mutation = immediate_response.headers.as_ref().unwrap();
            assert_eq!(header_mutation.set_headers.len(), 2);

            // Check body
            assert_eq!(
                String::from_utf8_lossy(&immediate_response.body),
                "Access denied"
            );
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    /// Tests creating a redirect response.
    ///
    /// Verifies that:
    /// - The correct response variant is created (ImmediateResponse)
    /// - The status code is correctly set
    /// - The Location header is correctly set
    /// - The body is empty
    #[test]
    fn test_add_redirect_response() {
        let status_code = 301;
        let location = "https://example.com/new-location";

        let response = add_redirect_response(status_code, location.to_string(), None);

        // Verify immediate response with redirect
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) =
            response.response
        {
            // Check status code
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301);

            // Check Location header
            let header_mutation = immediate_response.headers.as_ref().unwrap();
            let mut found_location = false;

            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "Location" {
                        found_location = true;
                        assert_eq!(String::from_utf8_lossy(&h.raw_value), location);
                    }
                }
            }

            assert!(found_location, "Location header not found");

            // Check body (should be empty)
            assert!(immediate_response.body.is_empty());
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    /// Tests creating redirect responses with different status codes.
    ///
    /// Verifies that:
    /// - Different redirect status codes (301, 302, 303, 307, 308) are correctly set
    #[test]
    fn test_add_redirect_response_different_status_codes() {
        // Test different redirect status codes
        let redirect_status_codes = vec![301, 302, 303, 307, 308];

        for status_code in redirect_status_codes {
            let response =
                add_redirect_response(status_code, "https://example.com".to_string(), None);

            if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) =
                response.response
            {
                assert_eq!(
                    immediate_response.status.as_ref().unwrap().code,
                    status_code as i32
                );
            } else {
                panic!("Expected ImmediateResponse");
            }
        }
    }
}
