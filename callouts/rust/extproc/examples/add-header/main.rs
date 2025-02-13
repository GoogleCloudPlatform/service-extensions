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
            vec![("header-request", "Value-request")],
            vec![],
            false,
        ))
    }

    async fn process_response_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(mutations::add_header_mutation(
            vec![("header-response", "Value-response")],
            vec![],
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

    // Using default config but enabling insecure server
    let mut config = Config::default();
    config.enable_insecure_server = true;

    let server = CalloutServer::new(config);
    let processor = AddHeaderProcessor::new();

    // Start all services
    let secure = server.spawn_grpc(processor.clone()).await;
    let insecure = server.spawn_insecure_grpc(processor.clone()).await;
    let health = server.spawn_health_check().await;

    // Wait for all services
    let _ = tokio::try_join!(secure, insecure, health)?;

    Ok(())
}