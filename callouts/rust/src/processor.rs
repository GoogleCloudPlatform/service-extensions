// src/processor.rs
use async_trait::async_trait;
use crate::envoy::service::ext_proc::v3::{ProcessingRequest, ProcessingResponse};
use thiserror::Error;

use crate::utils::mutations;

#[derive(Error, Debug)]
pub enum ProcessingError {
    #[error("Processing failed: {0}")]
    Failed(String),
}

#[async_trait]
pub trait ExtProcessor: Send + Sync + 'static {
    async fn process_request_headers(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_response_headers(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_request_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_response_body(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError>;
}

#[derive(Clone)]
pub struct HeaderMutationProcessor;

impl HeaderMutationProcessor {
    pub fn new() -> Self {
        Self
    }
}

#[async_trait]
impl ExtProcessor for HeaderMutationProcessor {
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