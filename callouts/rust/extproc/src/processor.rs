// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
use crate::envoy::service::ext_proc::v3::{ProcessingRequest, ProcessingResponse};
use async_trait::async_trait;
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
    async fn process_request_headers(
        &self,
        req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_response_headers(
        &self,
        req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_request_body(
        &self,
        req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError>;
    async fn process_response_body(
        &self,
        req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError>;
}
