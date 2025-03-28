use async_trait::async_trait;
use crate::envoy::service::ext_proc::v3::{ProcessingRequest, ProcessingResponse};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ProcessingError {
    #[error("Processing failed: {0}")]
    Failed(String),
    #[error("Authorization token is invalid: {0}")]
    PermissionDenied(String),
}

#[async_trait]
pub trait ExtProcessor: Send + Sync + 'static {
    async fn process_request_headers(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_response_headers(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_request_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_response_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
}