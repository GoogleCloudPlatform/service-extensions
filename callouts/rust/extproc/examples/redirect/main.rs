use async_trait::async_trait;
use ext_proc::{
    processor::{ExtProcessor, ProcessingError},
    envoy::service::ext_proc::v3::{
        ProcessingRequest,
        ProcessingResponse,
    },
    server::{CalloutServer, Config},
};
use ext_proc::utils::mutations;

/// RedirectProcessor returns a redirect response for all requests
#[derive(Clone)]
struct RedirectProcessor;

impl RedirectProcessor {
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for RedirectProcessor {
    async fn process_request_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(mutations::add_redirect_response(
            301,
            "http://service-extensions.com/redirect".to_string(),
        ))
    }

    async fn process_response_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    async fn process_request_body(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    async fn process_response_body(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }
}

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
    use super::*;
    use ext_proc::envoy::{
        config::core::v3::{HeaderMap, HeaderValue},
        service::ext_proc::v3::{
            HttpHeaders,
            processing_request::Request as ProcessingRequestVariant,
            processing_response::Response as ProcessingResponseVariant,
        },
    };

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

    #[tokio::test]
    async fn test_redirect_response() {
        let processor = RedirectProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(create_test_request_headers())),
            ..Default::default()
        };

        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Verify the response is an immediate response with redirect
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) = response.response {
            // Check status code
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301, "Expected 301 status code");

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

    #[tokio::test]
    async fn test_redirect_status_code() {
        let processor = RedirectProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(create_test_request_headers())),
            ..Default::default()
        };

        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Verify the status code is 301 (Moved Permanently)
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) = response.response {
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301);
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    #[tokio::test]
    async fn test_other_processor_methods() {
        let processor = RedirectProcessor::new();
        let empty_request = ProcessingRequest::default();

        // Test response headers method
        let response = processor.process_response_headers(&empty_request).await
            .expect("Failed to process response headers");
        assert_eq!(response, ProcessingResponse::default());

        // Test request body method
        let response = processor.process_request_body(&empty_request).await
            .expect("Failed to process request body");
        assert_eq!(response, ProcessingResponse::default());

        // Test response body method
        let response = processor.process_response_body(&empty_request).await
            .expect("Failed to process response body");
        assert_eq!(response, ProcessingResponse::default());
    }

    #[tokio::test]
    async fn test_empty_request() {
        let processor = RedirectProcessor::new();

        // Create an empty request
        let request = ProcessingRequest::default();

        // Even with an empty request, should still get a redirect
        let response = processor.process_request_headers(&request).await
            .expect("Failed to process empty request");

        // Verify still get a redirect response
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) = response.response {
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

    #[tokio::test]
    async fn test_different_request_types() {
        let processor = RedirectProcessor::new();

        // Test with different request types
        let request_types = vec![
            ProcessingRequestVariant::RequestHeaders(create_test_request_headers()),
            ProcessingRequestVariant::ResponseHeaders(create_test_request_headers()), // Using request headers as response headers for simplicity
            ProcessingRequestVariant::RequestBody(ext_proc::envoy::service::ext_proc::v3::HttpBody {
                body: b"test body".to_vec(),
                end_of_stream: true,
            }),
            ProcessingRequestVariant::ResponseBody(ext_proc::envoy::service::ext_proc::v3::HttpBody {
                body: b"test body".to_vec(),
                end_of_stream: true,
            }),
        ];

        for req_type in request_types {
            let request = ProcessingRequest {
                request: Some(req_type.clone()),
                ..Default::default()
            };

            // Only request headers should produce a redirect
            let response = processor.process_request_headers(&request).await
                .expect("Failed to process request");

            // Verify redirect response
            if let Some(ProcessingResponseVariant::ImmediateResponse(_)) = response.response {
                // This is expected for request headers
            } else {
                panic!("Expected ImmediateResponse for request headers");
            }
        }
    }

    #[tokio::test]
    async fn test_redirect_response_structure() {
        let processor = RedirectProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(create_test_request_headers())),
            ..Default::default()
        };

        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Verify the complete structure of the redirect response
        if let Some(ProcessingResponseVariant::ImmediateResponse(immediate_response)) = response.response {
            // Check status
            assert!(immediate_response.status.is_some(), "Status should be present");
            assert_eq!(immediate_response.status.as_ref().unwrap().code, 301);

            // Check headers
            assert!(immediate_response.headers.is_some(), "Headers should be present");

            // Check body (should be empty for redirects)
            assert!(immediate_response.body.is_empty(), "Body should be empty for redirects");

            // Check details (should be empty)
            assert!(immediate_response.details.is_empty(), "Details should be empty");

            // Check grpc_status (should be None for HTTP redirects)
            assert!(immediate_response.grpc_status.is_none(), "gRPC status should be None for HTTP redirects");
        } else {
            panic!("Expected ImmediateResponse");
        }
    }

    #[tokio::test]
    async fn test_compare_with_direct_mutation() {
        let processor = RedirectProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(create_test_request_headers())),
            ..Default::default()
        };

        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Create the expected response directly using the mutations helper
        let expected_response = mutations::add_redirect_response(
            301,
            "http://service-extensions.com/redirect".to_string(),
        );

        // Compare the responses
        assert_eq!(response, expected_response, "Response should match the direct mutation result");
    }
}