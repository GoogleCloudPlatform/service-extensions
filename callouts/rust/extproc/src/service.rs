use crate::envoy::service::ext_proc::v3::{
    external_processor_server::{ExternalProcessor, ExternalProcessorServer},
    ProcessingRequest, ProcessingResponse,
    processing_request::Request as ProcessingRequestType,
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
    type ProcessStream = Pin<Box<dyn Stream<Item = Result<ProcessingResponse, Status>> + Send + 'static>>;

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
                        let _ = tx.send(Err(Status::internal(e.to_string()))).await;
                        break;
                    }
                }
            }
        });

        Ok(Response::new(Box::pin(ReceiverStream::new(rx))))
    }
}