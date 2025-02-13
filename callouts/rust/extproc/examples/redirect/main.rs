use async_trait::async_trait;
use ext_proc::{
    processor::{ExtProcessor, ProcessingError},
    envoy::service::ext_proc::v3::{
        ProcessingRequest,
        ProcessingResponse,
        processing_response::Response,
        ImmediateResponse,
        HeaderMutation,
    },
    envoy::{
        config::core::v3::{HeaderValue, HeaderValueOption},
        r#type::v3::HttpStatus,
    },
    server::{CalloutServer, Config},
};

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
        let mut response = ProcessingResponse::default();
        response.response = Some(Response::ImmediateResponse(
            ImmediateResponse {
                status: Some(HttpStatus {
                    code: 301,
                }),
                headers: Some(HeaderMutation {
                    set_headers: vec![
                        HeaderValueOption {
                            header: Some(HeaderValue {
                                key: "Location".to_string(),
                                raw_value: b"http://service-extensions.com/redirect".to_vec(),
                                ..Default::default()
                            }),
                            append: None,
                            append_action: 0,
                            keep_empty_value: false,
                        }
                    ],
                    ..Default::default()
                }),
                body: Vec::new(),
                grpc_status: None,
                details: String::new(),
            },
        ));
        Ok(response)
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

    // Using default config but enabling insecure server
    let mut config = Config::default();
    config.enable_insecure_server = true;

    let server = CalloutServer::new(config);
    let processor = RedirectProcessor::new();

    // Start all services
    let secure = server.spawn_grpc(processor.clone()).await;
    let insecure = server.spawn_insecure_grpc(processor.clone()).await;
    let health = server.spawn_health_check().await;

    // Wait for all services
    let _ = tokio::try_join!(secure, insecure, health)?;

    Ok(())
}