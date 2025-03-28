use async_trait::async_trait;
use ext_proc::{
    processor::{ExtProcessor, ProcessingError},
    envoy::service::ext_proc::v3::{ProcessingRequest, ProcessingResponse},
    server::{CalloutServer, Config},
    utils::mutations,
};

/// AddHeaderProcessor adds custom headers to both requests and responses
#[derive(Clone)]
struct AddHeaderProcessor;

impl AddHeaderProcessor {
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for AddHeaderProcessor {
    async fn process_request_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(mutations::add_header_mutation(
            vec![("header-request".to_string(), "Value-request".to_string())],
            vec![],
            false,
            true,
        ))
    }

    async fn process_response_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(mutations::add_header_mutation(
            vec![("header-response".to_string(), "Value-response".to_string())],
            vec![],
            false,
            false,
        ))
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
    use super::*;
    use ext_proc::envoy::{
        config::core::v3::{HeaderMap, HeaderValue},
        service::ext_proc::v3::{
            processing_request::Request as ProcessingRequestVariant,
            processing_response::Response as ProcessingResponseVariant,
            HttpHeaders,
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

    #[tokio::test]
    async fn test_process_request_headers() {
        // Create processor
        let processor = AddHeaderProcessor::new();

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(create_test_request_headers())),
            ..Default::default()
        };

        // Process the request
        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Check if the response contains the expected header mutation
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();

            // Check if custom header is present
            let mut found_header = false;
            for header in header_mutation.set_headers {
                if let Some(h) = header.header {
                    if h.key == "header-request" {
                        found_header = true;
                        assert_eq!(
                            String::from_utf8_lossy(&h.raw_value),
                            "Value-request"
                        );
                    }
                }
            }

            assert!(found_header, "Custom request header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    #[tokio::test]
    async fn test_process_response_headers() {
        // Create processor
        let processor = AddHeaderProcessor::new();

        // Create request with response headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseHeaders(create_test_response_headers())),
            ..Default::default()
        };

        // Process the response headers
        let response = processor.process_response_headers(&request).await
            .expect("Failed to process response headers");

        // Check if the response contains the expected header mutation
        if let Some(ProcessingResponseVariant::ResponseHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();

            // Check if custom header is present
            let mut found_header = false;
            for header in header_mutation.set_headers {
                if let Some(h) = header.header {
                    if h.key == "header-response" {
                        found_header = true;
                        assert_eq!(
                            String::from_utf8_lossy(&h.raw_value),
                            "Value-response"
                        );
                    }
                }
            }

            assert!(found_header, "Custom response header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

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
        );

        // Check if all headers are present
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();

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
                            assert_eq!(
                                String::from_utf8_lossy(&h.raw_value),
                                *expected_value
                            );
                        }
                    }
                }
                assert!(found, "Header {} not found", expected_key);
            }
        } else {
            panic!("Unexpected response type");
        }
    }

    #[tokio::test]
    async fn test_header_removal() {
        // Test that headers can be removed from a request
        let response = mutations::add_header_mutation(
            vec![("new-header".to_string(), "new-value".to_string())],
            vec!["user-agent".to_string(), "host".to_string()],
            false,
            true,
        );

        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();

            // Check that the headers to remove are present
            assert_eq!(header_mutation.remove_headers.len(), 2);
            assert!(header_mutation.remove_headers.contains(&"user-agent".to_string()));
            assert!(header_mutation.remove_headers.contains(&"host".to_string()));

            // Check that the new header is present
            let mut found_new_header = false;
            for header in header_mutation.set_headers {
                if let Some(h) = header.header {
                    if h.key == "new-header" {
                        found_new_header = true;
                        assert_eq!(
                            String::from_utf8_lossy(&h.raw_value),
                            "new-value"
                        );
                    }
                }
            }

            assert!(found_new_header, "New header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    #[tokio::test]
    async fn test_clear_route_cache() {
        // Test with clear_route_cache set to true for request headers
        let response = mutations::add_header_mutation(
            vec![("test-header".to_string(), "test-value".to_string())],
            vec![],
            true,
            true,
        );

        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let common_response = headers_response.response.unwrap();

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
        );

        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let common_response = headers_response.response.unwrap();

            // Check that clear_route_cache is set to false
            assert!(!common_response.clear_route_cache);
        } else {
            panic!("Unexpected response type");
        }
    }

    #[tokio::test]
    async fn test_response_header_mutation() {
        // Test adding headers to a response
        let response = mutations::add_header_mutation(
            vec![
                ("response-header1".to_string(), "response-value1".to_string()),
                ("response-header2".to_string(), "response-value2".to_string()),
            ],
            vec![],
            false,
            false,
        );

        if let Some(ProcessingResponseVariant::ResponseHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();

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
                            assert_eq!(
                                String::from_utf8_lossy(&h.raw_value),
                                *expected_value
                            );
                        }
                    }
                }
                assert!(found, "Header {} not found", expected_key);
            }
        } else {
            panic!("Unexpected response type");
        }
    }

    #[tokio::test]
    async fn test_response_header_removal() {
        // Test that headers can be removed from a response
        let response = mutations::add_header_mutation(
            vec![("new-response-header".to_string(), "new-response-value".to_string())],
            vec!["content-type".to_string(), "server".to_string()],
            false,
            false,
        );

        if let Some(ProcessingResponseVariant::ResponseHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();

            // Check that the headers to remove are present
            assert_eq!(header_mutation.remove_headers.len(), 2);
            assert!(header_mutation.remove_headers.contains(&"content-type".to_string()));
            assert!(header_mutation.remove_headers.contains(&"server".to_string()));

            // Check that the new header is present
            let mut found_new_header = false;
            for header in header_mutation.set_headers {
                if let Some(h) = header.header {
                    if h.key == "new-response-header" {
                        found_new_header = true;
                        assert_eq!(
                            String::from_utf8_lossy(&h.raw_value),
                            "new-response-value"
                        );
                    }
                }
            }

            assert!(found_new_header, "New response header not found");
        } else {
            panic!("Unexpected response type");
        }
    }
}