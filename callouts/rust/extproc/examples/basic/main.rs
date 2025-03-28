use async_trait::async_trait;
use ext_proc::{
    processor::{ExtProcessor, ProcessingError},
    envoy::service::ext_proc::v3::{
        ProcessingRequest,
        ProcessingResponse,
        processing_request::Request as ProcessingRequestVariant,
    },
    server::{CalloutServer, Config},
    utils::mutations,
};

/// BasicProcessor demonstrates headers and body modifications
#[derive(Clone)]
struct BasicProcessor;

impl BasicProcessor {
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for BasicProcessor {
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

    async fn process_request_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        if let Some(ProcessingRequestVariant::RequestBody(body)) = &req.request {
            return Ok(mutations::add_body_string_mutation("new-body-request".to_string(), true, false));
        }

        // If no body, just pass through
        Ok(ProcessingResponse::default())
    }

    async fn process_response_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        if let Some(ProcessingRequestVariant::ResponseBody(body)) = &req.request {
            return Ok(mutations::add_body_string_mutation("new-body-response".to_string(), false, false));
        }

        // If no body, just pass through
        Ok(ProcessingResponse::default())
    }
}

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
    use super::*;
    use ext_proc::envoy::{
        config::core::v3::{HeaderMap, HeaderValue},
        service::ext_proc::v3::{
            HttpBody,
            HttpHeaders,
            processing_request::Request as ProcessingRequestVariant,
            processing_response::Response as ProcessingResponseVariant,
            body_mutation::Mutation as BodyMutationType,
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
        let processor = BasicProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(create_test_request_headers())),
            ..Default::default()
        };

        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Verify the response adds the expected header
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
        let processor = BasicProcessor::new();

        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseHeaders(create_test_response_headers())),
            ..Default::default()
        };

        let response = processor.process_response_headers(&request).await
            .expect("Failed to process response headers");

        // Verify the response adds the expected header
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

        let response = processor.process_request_body(&request).await
            .expect("Failed to process request body");

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

            if let Some(BodyMutationType::Body(new_body)) = body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(&new_body),
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

        let response = processor.process_response_body(&request).await
            .expect("Failed to process response body");

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

            if let Some(BodyMutationType::Body(new_body)) = body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(&new_body),
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

    #[tokio::test]
    async fn test_end_to_end_processing() {
        let processor = BasicProcessor::new();

        // 1. Process request headers
        let req_headers = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(create_test_request_headers())),
            ..Default::default()
        };

        let resp_headers = processor.process_request_headers(&req_headers).await.unwrap();

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
            request: Some(ProcessingRequestVariant::ResponseHeaders(create_test_response_headers())),
            ..Default::default()
        };

        let resp_headers_resp = processor.process_response_headers(&resp_headers_req).await.unwrap();

        // 4. Process response body
        let resp_body_req = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseBody(HttpBody {
                body: b"original response body".to_vec(),
                end_of_stream: true,
            })),
            ..Default::default()
        };

        let resp_body_resp = processor.process_response_body(&resp_body_req).await.unwrap();

        // Verify all responses have the expected modifications

        // Request headers should have "header-request" added
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = resp_headers.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();
            let mut found = false;
            for header in header_mutation.set_headers {
                if let Some(h) = header.header {
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
            let body_mutation = body_response.response.unwrap().body_mutation.unwrap();
            if let Some(BodyMutationType::Body(new_body)) = body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(&new_body),
                    "new-body-request"
                );
            } else {
                panic!("Expected Body mutation type for request body");
            }
        } else {
            panic!("Unexpected response type for request body");
        }

        // Response headers should have "header-response" added
        if let Some(ProcessingResponseVariant::ResponseHeaders(headers_response)) = resp_headers_resp.response {
            let header_mutation = headers_response.response.unwrap().header_mutation.unwrap();
            let mut found = false;
            for header in header_mutation.set_headers {
                if let Some(h) = header.header {
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
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = resp_body_resp.response {
            let body_mutation = body_response.response.unwrap().body_mutation.unwrap();
            if let Some(BodyMutationType::Body(new_body)) = body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(&new_body),
                    "new-body-response"
                );
            } else {
                panic!("Expected Body mutation type for response body");
            }
        } else {
            panic!("Unexpected response type for response body");
        }
    }
}