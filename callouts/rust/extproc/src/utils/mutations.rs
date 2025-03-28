use crate::envoy::{
    config::core::v3::{HeaderValue, HeaderValueOption},
    service::ext_proc::v3::{
        ProcessingResponse,
        HeadersResponse,
        CommonResponse,
        HeaderMutation,
        processing_response::Response as ProcessingResponseType,
    },
};
use crate::envoy::r#type::v3::HttpStatus;
use crate::envoy::service::ext_proc::v3::{body_mutation, processing_response, BodyMutation, BodyResponse, ImmediateResponse};
use crate::envoy::service::ext_proc::v3::processing_response::Response;
#[allow(deprecated)]
pub fn add_header_mutation(
    headers_to_add: Vec<(String, String)>,
    headers_to_remove: Vec<String>,
    clear_route_cache: bool,
    is_request: bool,
) -> ProcessingResponse {
    let mut header_mutation = HeaderMutation::default();

    // Add headers
    header_mutation.set_headers = headers_to_add
        .into_iter()
        .map(|(key, value)| HeaderValueOption {
            header: Some(HeaderValue {
                key: key.to_string(),
                raw_value: value.as_bytes().to_vec(),
                ..Default::default()
            }),
            append: None,  // Keep for backwards compatibility
            append_action: 0,  // APPEND_NONE
            keep_empty_value: false,
        })
        .collect();

    // Remove headers
    header_mutation.remove_headers = headers_to_remove
        .into_iter()
        .map(String::from)
        .collect();

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

// Add body string mutation
pub fn add_body_string_mutation(body: String, is_request: bool, clear_route_cache: bool) -> ProcessingResponse {
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

// Clear body mutation
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

#[allow(deprecated)]
pub fn add_immediate_response(
    status_code: u32,
    headers: Vec<(String, String)>,
    body: Option<Vec<u8>>,
) -> ProcessingResponse {
    let mut header_mutation = HeaderMutation::default();

    // Add headers
    header_mutation.set_headers = headers
        .into_iter()
        .map(|(key, value)| HeaderValueOption {
            header: Some(HeaderValue {
                key,
                raw_value: value.into_bytes(),
                ..Default::default()
            }),
            append: None, // Keep for backwards compatibility
            append_action: 0,  // APPEND_NONE
            keep_empty_value: false,
        })
        .collect();

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

pub fn add_redirect_response(
    status_code: u32,
    location: String,
) -> ProcessingResponse {
    add_immediate_response(
        status_code,
        vec![("Location".to_string(), location)],
        None,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::envoy::service::ext_proc::v3::processing_response::Response as ProcessingResponseVariant;

    #[test]
    fn test_add_header_mutation_request() {
        // Test adding headers to a request
        let headers_to_add = vec![
            ("X-Test-Header".to_string(), "test-value".to_string()),
            ("X-Another-Header".to_string(), "another-value".to_string()),
        ];
        let headers_to_remove = vec!["X-Remove-Me".to_string()];

        let response = add_header_mutation(headers_to_add, headers_to_remove, true, true);

        // Verify request headers response
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            // Use as_ref() to borrow the contents instead of taking ownership
            let header_mutation = headers_response.response.as_ref().unwrap().header_mutation.as_ref().unwrap();

            // Check added headers
            assert_eq!(header_mutation.set_headers.len(), 2);
            assert_eq!(
                header_mutation.set_headers[0].header.as_ref().unwrap().key,
                "X-Test-Header"
            );
            assert_eq!(
                String::from_utf8_lossy(&header_mutation.set_headers[0].header.as_ref().unwrap().raw_value),
                "test-value"
            );

            // Check removed headers
            assert_eq!(header_mutation.remove_headers.len(), 1);
            assert_eq!(header_mutation.remove_headers[0], "X-Remove-Me");

            // Check route cache clearing
            assert!(headers_response.response.as_ref().unwrap().clear_route_cache);
        } else {
            panic!("Expected RequestHeaders response");
        }
    }

    #[test]
    fn test_add_header_mutation_response() {
        // Test adding headers to a response
        let headers_to_add = vec![
            ("X-Test-Header".to_string(), "test-value".to_string()),
        ];
        let headers_to_remove = vec![];

        let response = add_header_mutation(headers_to_add, headers_to_remove, false, false);

        // Verify response headers response
        if let Some(ProcessingResponseVariant::ResponseHeaders(_)) = response.response {
            // Test passed
        } else {
            panic!("Expected ResponseHeaders response");
        }
    }

    #[test]
    fn test_add_body_string_mutation_request() {
        let body = "Modified request body";
        let response = add_body_string_mutation(body.to_string(), true, false);

        // Verify request body response
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response.response.as_ref().unwrap().body_mutation.as_ref().unwrap();

            if let Some(body_mutation::Mutation::Body(modified_body)) = &body_mutation.mutation {
                assert_eq!(String::from_utf8_lossy(modified_body), body);
            } else {
                panic!("Expected Body mutation");
            }
        } else {
            panic!("Expected RequestBody response");
        }
    }

    #[test]
    fn test_add_body_string_mutation_response() {
        let body = "Modified response body";
        let response = add_body_string_mutation(body.to_string(), false, true);

        // Verify response body response
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response.response.as_ref().unwrap().body_mutation.as_ref().unwrap();

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

    #[test]
    fn test_add_body_clear_mutation_request() {
        let response = add_body_clear_mutation(true, false);

        // Verify request body response with clear body
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response.response.as_ref().unwrap().body_mutation.as_ref().unwrap();

            if let Some(body_mutation::Mutation::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear);
            } else {
                panic!("Expected ClearBody mutation");
            }
        } else {
            panic!("Expected RequestBody response");
        }
    }

    #[test]
    fn test_add_body_clear_mutation_response() {
        let response = add_body_clear_mutation(false, true);

        // Verify response body response with clear body
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            // Use as_ref() to borrow the contents
            let body_mutation = body_response.response.as_ref().unwrap().body_mutation.as_ref().unwrap();

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

    #[test]
    fn test_add_immediate_response() {
        let status_code = 403;
        let headers = vec![
            ("X-Test-Header".to_string(), "test-value".to_string()),
            ("Content-Type".to_string(), "text/plain".to_string()),
        ];
        let body = Some(b"Access denied".to_vec());

        let response = add_immediate_response(status_code, headers, body);

        // Verify immediate response
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) = response.response {
            // Check status code
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 403);

            // Check headers
            let header_mutation = immediate_response.headers.as_ref().unwrap();
            assert_eq!(header_mutation.set_headers.len(), 2);

            // Check body
            assert_eq!(String::from_utf8_lossy(&immediate_response.body), "Access denied");
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    #[test]
    fn test_add_redirect_response() {
        let status_code = 301;
        let location = "https://example.com/new-location";

        let response = add_redirect_response(status_code, location.to_string());

        // Verify immediate response with redirect
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) = response.response {
            // Check status code
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301);

            // Check Location header
            let header_mutation = immediate_response.headers.as_ref().unwrap();
            let mut found_location = false;

            for header in &header_mutation.set_headers {
                if let Some(h) = &header.header {
                    if h.key == "Location" {
                        found_location = true;
                        assert_eq!(
                            String::from_utf8_lossy(&h.raw_value),
                            location
                        );
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

    #[test]
    fn test_add_redirect_response_different_status_codes() {
        // Test different redirect status codes
        let redirect_status_codes = vec![301, 302, 303, 307, 308];

        for status_code in redirect_status_codes {
            let response = add_redirect_response(status_code, "https://example.com".to_string());

            if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) = response.response {
                assert_eq!(immediate_response.status.as_ref().unwrap().code, status_code as i32);
            } else {
                panic!("Expected ImmediateResponse");
            }
        }
    }
}