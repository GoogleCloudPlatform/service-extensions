use crate::processor::ExtProcessor;
use crate::service::ExtProcService;
use log::{info, error};
use tokio::net::TcpListener;
use tonic::transport::{Identity, Server};
use hyper::{Body, Response, Server as HyperServer};
use std::convert::Infallible;
use std::path::PathBuf;
use futures::Stream;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::error;

#[derive(Clone)]
pub struct Config {
    pub address: String,
    pub plaintext_address: Option<String>,
    pub health_check_address: String,
    pub cert_file: PathBuf,
    pub key_file: PathBuf,
    pub enable_plaintext_server: bool,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            address: "0.0.0.0:443".to_string(),
            plaintext_address: Some("0.0.0.0:8080".to_string()),
            health_check_address: "0.0.0.0:80".to_string(),
            cert_file: "extproc/ssl_creds/localhost.crt".into(),
            key_file: "extproc/ssl_creds/localhost.key".into(),
            enable_plaintext_server: true,
        }
    }
}

#[derive(Clone)]
pub struct CalloutServer {
    config: Config,
}

// Custom TcpListener stream for health check
struct TcpListenerStream {
    listener: TcpListener,
}

impl Stream for TcpListenerStream {
    type Item = Result<tokio::net::TcpStream, std::io::Error>;

    fn poll_next(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        let listener = &self.listener;
        match listener.poll_accept(cx) {
            Poll::Ready(Ok((socket, _addr))) => Poll::Ready(Some(Ok(socket))),
            Poll::Ready(Err(err)) => Poll::Ready(Some(Err(err))),
            Poll::Pending => Poll::Pending,
        }
    }
}

impl CalloutServer {
    pub fn new(config: Config) -> Self {
        Self { config }
    }

    pub fn with_default_config() -> Self {
        Self {
            config: Config::default(),
        }
    }

    pub async fn spawn_grpc<P: ExtProcessor + Clone + Send + 'static>(
        &self,
        processor: P,
    ) -> tokio::task::JoinHandle<()> {
        let server = self.clone();
        let processor = processor.clone();
        tokio::spawn(async move {
            if let Err(e) = server.start_grpc(processor).await {
                error!("Failed to start secure server: {}", e);
            }
        })
    }

    pub async fn spawn_plaintext_grpc<P: ExtProcessor + Clone + Send + 'static>(
        &self,
        processor: P,
    ) -> tokio::task::JoinHandle<()> {
        let server = self.clone();
        let processor = processor.clone();
        tokio::spawn(async move {
            if let Err(e) = server.start_plaintext_grpc(processor).await {
                error!("Failed to start plaintext server: {}", e);
            }
        })
    }

    pub async fn spawn_health_check(&self) -> tokio::task::JoinHandle<()> {
        let server = self.clone();
        tokio::spawn(async move {
            if let Err(e) = server.start_health_check().await {
                error!("Failed to start health check server: {}", e);
            }
        })
    }

    async fn start_grpc<P: ExtProcessor + 'static>(
        &self,
        processor: P,
    ) -> Result<(), Box<dyn error::Error + Send + Sync>> {
        // Check if certificate files exist
        if !self.config.cert_file.exists() {
            return Err(format!("Certificate file not found: {:?}", self.config.cert_file).into());
        }
        if !self.config.key_file.exists() {
            return Err(format!("Key file not found: {:?}", self.config.key_file).into());
        }

        info!("Loading TLS certificates...");
        let cert = tokio::fs::read(&self.config.cert_file).await
            .map_err(|e| format!("Failed to read certificate file: {}", e))?;
        let key = tokio::fs::read(&self.config.key_file).await
            .map_err(|e| format!("Failed to read key file: {}", e))?;

        let identity = Identity::from_pem(cert, key);
        let addr = self.config.address.parse()
            .map_err(|e| format!("Failed to parse secure address: {}", e))?;

        let service = ExtProcService::new(processor);

        info!("Starting secure gRPC server on {}", self.config.address);
        Server::builder()
            .tls_config(tonic::transport::ServerTlsConfig::new().identity(identity))
            .map_err(|e| format!("Failed to configure TLS: {}", e))?
            .add_service(service.into_server())
            .serve(addr)
            .await
            .map_err(|e| format!("Secure server error: {}", e))?;

        Ok(())
    }

    async fn start_plaintext_grpc<P: ExtProcessor + 'static>(
        &self,
        processor: P,
    ) -> Result<(), Box<dyn error::Error + Send + Sync>> {
        if !self.config.enable_plaintext_server {
            info!("Plaintext server is disabled");
            return Ok(());
        }

        let addr = self.config.plaintext_address.as_ref()
            .ok_or("Plaintext address not configured")?
            .parse()?;
        let service = ExtProcService::new(processor);

        info!("Starting plaintext gRPC server on {}", self.config.plaintext_address.as_ref().unwrap());
        Server::builder()
            .add_service(service.into_server())
            .serve(addr)
            .await?;

        Ok(())
    }

    async fn start_health_check(&self) -> Result<(), Box<dyn error::Error + Send + Sync>> {
        let listener = TcpListener::bind(&self.config.health_check_address).await?;
        info!("Starting health check server on {}", self.config.health_check_address);

        let make_service = hyper::service::make_service_fn(|_| async {
            Ok::<_, Infallible>(hyper::service::service_fn(|_| async {
                Ok::<_, Infallible>(Response::new(Body::from("")))
            }))
        });

        let tcp_listener_stream = TcpListenerStream { listener };

        let server = HyperServer::builder(hyper::server::accept::from_stream(tcp_listener_stream))
            .serve(make_service);

        server.await?;
        Ok(())
    }
}