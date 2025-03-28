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

/// AddBodyProcessor demonstrates body modifications
#[derive(Clone)]
struct AddBodyProcessor;

impl AddBodyProcessor {
    fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for AddBodyProcessor {
    async fn process_request_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    async fn process_response_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
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
    use super::*;
    use ext_proc::envoy::{
        service::ext_proc::v3::{
            HttpBody,
            processing_request::Request as ProcessingRequestVariant,
            processing_response::Response as ProcessingResponseVariant,
            body_mutation::Mutation as BodyMutationType,
        },
    };

    fn create_test_request_body(content: &[u8], end_of_stream: bool) -> ProcessingRequest {
        ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestBody(HttpBody {
                body: content.to_vec(),
                end_of_stream,
            })),
            ..Default::default()
        }
    }

    fn create_test_response_body(content: &[u8], end_of_stream: bool) -> ProcessingRequest {
        ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseBody(HttpBody {
                body: content.to_vec(),
                end_of_stream,
            })),
            ..Default::default()
        }
    }

    #[tokio::test]
    async fn test_process_request_body() {
        let processor = AddBodyProcessor::new();
        let body_content = b"test request body";

        let request = create_test_request_body(body_content, true);

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

            // Verify clear_route_cache is false
            assert!(!common_response.clear_route_cache, "clear_route_cache should be false");
        } else {
            panic!("Expected RequestBody response");
        }
    }

    #[tokio::test]
    async fn test_process_response_body() {
        let processor = AddBodyProcessor::new();
        let body_content = b"test response body";

        let request = create_test_response_body(body_content, true);

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

            // Verify clear_route_cache is false
            assert!(!common_response.clear_route_cache, "clear_route_cache should be false");
        } else {
            panic!("Expected ResponseBody response");
        }
    }

    #[tokio::test]
    async fn test_empty_request_body() {
        let processor = AddBodyProcessor::new();

        // Create a request with no body
        let request = ProcessingRequest::default();

        let response = processor.process_request_body(&request).await
            .expect("Failed to process empty request body");

        // For empty body, expect a default response (pass-through)
        assert_eq!(response, ProcessingResponse::default(), "Empty body should result in default response");
    }

    #[tokio::test]
    async fn test_empty_response_body() {
        let processor = AddBodyProcessor::new();

        // Create a request with no body
        let request = ProcessingRequest::default();

        let response = processor.process_response_body(&request).await
            .expect("Failed to process empty response body");

        // For empty body, expect a default response (pass-through)
        assert_eq!(response, ProcessingResponse::default(), "Empty body should result in default response");
    }

    #[tokio::test]
    async fn test_clear_request_body() {
        // Test the clear body mutation directly
        let response = mutations::add_body_clear_mutation(true, false);

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

            if let Some(BodyMutationType::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear, "ClearBody should be true");
            } else {
                panic!("Expected ClearBody mutation type");
            }

            // Verify clear_route_cache is false
            assert!(!common_response.clear_route_cache, "clear_route_cache should be false");
        } else {
            panic!("Expected RequestBody response");
        }
    }

    #[tokio::test]
    async fn test_clear_response_body() {
        // Test the clear body mutation directly
        let response = mutations::add_body_clear_mutation(false, false);

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

            if let Some(BodyMutationType::ClearBody(clear)) = body_mutation.mutation {
                assert!(clear, "ClearBody should be true");
            } else {
                panic!("Expected ClearBody mutation type");
            }

            // Verify clear_route_cache is false
            assert!(!common_response.clear_route_cache, "clear_route_cache should be false");
        } else {
            panic!("Expected ResponseBody response");
        }
    }

    #[tokio::test]
    async fn test_body_with_route_cache_clearing() {
        // Test body mutation with route cache clearing
        let response = mutations::add_body_string_mutation("test-body".to_string(), true, true);

        // Verify the response type and content
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();

            // Verify clear_route_cache is true
            assert!(common_response.clear_route_cache, "clear_route_cache should be true");
        } else {
            panic!("Expected RequestBody response");
        }
    }

    #[tokio::test]
    async fn test_large_body_replacement() {
        let processor = AddBodyProcessor::new();

        // Create a large body
        let large_body = vec![b'X'; 10000];
        let request = create_test_request_body(&large_body, true);

        let response = processor.process_request_body(&request).await
            .expect("Failed to process large request body");

        // Verify the response replaces the large body
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

            if let Some(BodyMutationType::Body(new_body)) = body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(&new_body),
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

    #[tokio::test]
    async fn test_streaming_body() {
        let processor = AddBodyProcessor::new();

        // Create a body with end_of_stream set to false (simulating streaming)
        let request = create_test_request_body(b"streaming chunk", false);

        let response = processor.process_request_body(&request).await
            .expect("Failed to process streaming request body");

        // Verify the response still replaces the body
        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

            if let Some(BodyMutationType::Body(new_body)) = body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(&new_body),
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

    #[tokio::test]
    async fn test_modified_processor() {
        // Create a custom processor that uses clear body mutation for requests
        // and string replacement for responses
        struct CustomBodyProcessor;

        #[async_trait]
        impl ExtProcessor for CustomBodyProcessor {
            async fn process_request_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
                Ok(ProcessingResponse::default())
            }

            async fn process_response_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
                Ok(ProcessingResponse::default())
            }

            async fn process_request_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
                if let Some(ProcessingRequestVariant::RequestBody(_)) = &req.request {
                    return Ok(mutations::add_body_clear_mutation(true, false));
                }
                Ok(ProcessingResponse::default())
            }

            async fn process_response_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
                if let Some(ProcessingRequestVariant::ResponseBody(_)) = &req.request {
                    return Ok(mutations::add_body_string_mutation("custom-response".to_string(), false, true));
                }
                Ok(ProcessingResponse::default())
            }
        }

        let processor = CustomBodyProcessor;

        // Test request body processing (should clear the body)
        let request = create_test_request_body(b"test body", true);
        let response = processor.process_request_body(&request).await
            .expect("Failed to process request body");

        if let Some(ProcessingResponseVariant::RequestBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

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
        let response = processor.process_response_body(&request).await
            .expect("Failed to process response body");

        if let Some(ProcessingResponseVariant::ResponseBody(body_response)) = response.response {
            let common_response = body_response.response.unwrap();
            let body_mutation = common_response.body_mutation.unwrap();

            if let Some(BodyMutationType::Body(new_body)) = body_mutation.mutation {
                assert_eq!(
                    String::from_utf8_lossy(&new_body),
                    "custom-response",
                    "Response body was not replaced with expected content"
                );
            } else {
                panic!("Expected Body mutation type for response");
            }

            // Verify clear_route_cache is true
            assert!(common_response.clear_route_cache, "clear_route_cache should be true for response");
        } else {
            panic!("Expected ResponseBody response");
        }
    }
}