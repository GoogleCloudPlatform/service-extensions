// src/main.rs
use ext_proc::{processor::HeaderMutationProcessor, service::ExtProcService};
use log::info;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();

    let addr = "127.0.0.1:8080";
    let processor = HeaderMutationProcessor::new();
    let service = ExtProcService::new(processor);

    info!("Starting ext_proc service on {}", addr);
    service.run(addr).await?;

    Ok(())
}