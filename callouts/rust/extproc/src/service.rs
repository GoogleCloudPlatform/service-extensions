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
use crate::envoy::service::ext_proc::v3::{
    external_processor_server::{ExternalProcessor, ExternalProcessorServer},
    processing_request::Request as ProcessingRequestType,
    ProcessingRequest, ProcessingResponse,
};
use crate::processor::ExtProcessor;
use futures::Stream;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use tonic::{Request, Response, Status};

pub struct ExtProcService {
    processor: Arc<dyn ExtProcessor>,
}

impl ExtProcService {
    pub fn new<P: ExtProcessor + 'static>(processor: P) -> Self {
        Self {
            processor: Arc::new(processor),
        }
    }

    pub fn into_server(self) -> ExternalProcessorServer<Self> {
        ExternalProcessorServer::new(self)
    }
}

#[tonic::async_trait]
impl ExternalProcessor for ExtProcService {
    type ProcessStream =
        Pin<Box<dyn Stream<Item = Result<ProcessingResponse, Status>> + Send + 'static>>;

    async fn process(
        &self,
        request: Request<tonic::Streaming<ProcessingRequest>>,
    ) -> Result<Response<Self::ProcessStream>, Status> {
        let mut stream = request.into_inner();
        let (tx, rx) = mpsc::channel(32);
        let processor = self.processor.clone();

        tokio::spawn(async move {
            while let Ok(Some(req)) = stream.message().await {
                let response = match &req.request {
                    Some(request) => match request {
                        ProcessingRequestType::RequestHeaders(_) => {
                            processor.process_request_headers(&req).await
                        }
                        ProcessingRequestType::ResponseHeaders(_) => {
                            processor.process_response_headers(&req).await
                        }
                        ProcessingRequestType::RequestBody(_) => {
                            processor.process_request_body(&req).await
                        }
                        ProcessingRequestType::ResponseBody(_) => {
                            processor.process_response_body(&req).await
                        }
                        _ => Ok(ProcessingResponse::default()),
                    },
                    None => Ok(ProcessingResponse::default()),
                };

                match response {
                    Ok(resp) => {
                        if tx.send(Ok(resp)).await.is_err() {
                            break;
                        }
                    }
                    Err(e) => {
                        let status = match e {
                            crate::processor::ProcessingError::PermissionDenied(msg) => {
                                Status::permission_denied(msg)
                            }
                            crate::processor::ProcessingError::Failed(msg) => {
                                Status::internal(msg)
                            }
                        };
                        let _ = tx.send(Err(status)).await;
                        break;
                    }
                }
            }
        });

        Ok(Response::new(Box::pin(ReceiverStream::new(rx))))
    }
}
