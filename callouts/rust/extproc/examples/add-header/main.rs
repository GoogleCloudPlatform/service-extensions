use async_trait::async_trait;
use ext_proc::{
    processor::{ExtProcessor, ProcessingError},
    envoy::service::ext_proc::v3::{ProcessingRequest, ProcessingResponse},
    service::ExtProcService,
    utils::mutations,
};
use log::info;

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

    let addr = "0.0.0.0:8080";
    let processor = AddHeaderProcessor::new();
    let service = ExtProcService::new(processor);

    info!("Starting add-header ext_proc service on {}", addr);
    service.run(addr).await?;

    Ok(())
}