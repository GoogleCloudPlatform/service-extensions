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
//! # CalloutServer Module
//!
//! This module provides the server infrastructure for running Envoy external processors.
//! It handles the setup and management of gRPC servers (both secure and plaintext) and
//! a health check HTTP server.
//!
//! ## Overview
//!
//! The `CalloutServer` is responsible for:
//!
//! - Running a plaintext gRPC server (default, enabled by default)
//! - Optionally providing a secure TLS gRPC server when enabled via `enable_tls`
//! - Running a simple HTTP health check endpoint
//! - Managing the lifecycle of these servers
//!
//! This infrastructure allows external processors to focus on implementing their
//! processing logic without worrying about server setup and management.

use crate::processor::ExtProcessor;
use crate::service::ExtProcService;
use futures::Stream;
use hyper::{Body, Response, Server as HyperServer};
use log::{error, info};
use std::convert::Infallible;
use std::error;
use std::path::PathBuf;
use std::pin::Pin;
use std::task::{Context, Poll};
use tokio::net::TcpListener;
use tonic::transport::{Identity, Server};

/// Configuration for the `CalloutServer`.
///
/// This struct contains all the settings needed to configure the various
/// server endpoints, including addresses and TLS certificate paths.
#[derive(Clone)]
pub struct Config {
    /// Address for the secure gRPC server (format: "host:port")
    pub address: String,

    /// Optional address for the plaintext gRPC server (format: "host:port")
    pub plaintext_address: Option<String>,

    /// Address for the health check HTTP server (format: "host:port")
    pub health_check_address: String,

    /// Path to the TLS certificate file
    pub cert_file: PathBuf,

    /// Path to the TLS key file
    pub key_file: PathBuf,

    /// Whether to enable the plaintext gRPC server (default: true)
    pub enable_plaintext_server: bool,

    /// Whether to enable the TLS gRPC server (default: false)
    pub enable_tls: bool,
}

impl Default for Config {
    /// Creates a default configuration for the `CalloutServer`.
    ///
    /// Default values:
    /// - Plaintext gRPC server on 0.0.0.0:8080 (enabled by default)
    /// - TLS gRPC server on 0.0.0.0:443 (disabled by default)
    /// - Health check server on 0.0.0.0:80
    /// - TLS certificates at "extproc/ssl_creds/localhost.crt" and "extproc/ssl_creds/localhost.key"
    fn default() -> Self {
        Self {
            address: "0.0.0.0:443".to_string(),
            plaintext_address: Some("0.0.0.0:8080".to_string()),
            health_check_address: "0.0.0.0:80".to_string(),
            cert_file: "extproc/ssl_creds/localhost.crt".into(),
            key_file: "extproc/ssl_creds/localhost.key".into(),
            enable_plaintext_server: true,
            enable_tls: false,
        }
    }
}

/// Server for hosting Envoy external processors.
///
/// The `CalloutServer` manages three separate servers:
/// 1. A secure gRPC server with TLS for production use
/// 2. An optional plaintext gRPC server for development/testing
/// 3. A simple HTTP health check endpoint
///
/// Each server runs in its own task and can be spawned separately.
#[derive(Clone)]
pub struct CalloutServer {
    /// Configuration for the server
    config: Config,
}

/// Custom stream adapter for the TcpListener used by the health check server.
///
/// This adapter implements the `Stream` trait to make the TcpListener compatible
/// with hyper's `accept::from_stream` function.
struct TcpListenerStream {
    /// The underlying TCP listener
    listener: TcpListener,
}

impl Stream for TcpListenerStream {
    type Item = Result<tokio::net::TcpStream, std::io::Error>;

    /// Polls the TCP listener for new connections.
    ///
    /// This method is called by the runtime to check if a new connection is available.
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
    /// Creates a new `CalloutServer` with the specified configuration.
    ///
    /// # Arguments
    ///
    /// * `config` - The configuration for the server
    ///
    /// # Returns
    ///
    /// A new `CalloutServer` instance
    pub fn new(config: Config) -> Self {
        Self { config }
    }

    /// Creates a new `CalloutServer` with default configuration.
    ///
    /// # Returns
    ///
    /// A new `CalloutServer` instance with default settings
    pub fn with_default_config() -> Self {
        Self {
            config: Config::default(),
        }
    }

    /// Spawns the secure gRPC server in a new task.
    ///
    /// This method starts the TLS-enabled gRPC server that hosts the external processor.
    ///
    /// # Arguments
    ///
    /// * `processor` - The external processor implementation to host
    ///
    /// # Returns
    ///
    /// A `JoinHandle` for the spawned task
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

    /// Spawns the plaintext gRPC server in a new task.
    ///
    /// This method starts the non-TLS gRPC server that hosts the external processor.
    /// This server is intended for development and testing purposes.
    ///
    /// # Arguments
    ///
    /// * `processor` - The external processor implementation to host
    ///
    /// # Returns
    ///
    /// A `JoinHandle` for the spawned task
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

    /// Spawns the health check HTTP server in a new task.
    ///
    /// This method starts a simple HTTP server that responds to all requests with
    /// an empty 200 OK response, which can be used for health checking.
    ///
    /// # Returns
    ///
    /// A `JoinHandle` for the spawned task
    pub async fn spawn_health_check(&self) -> tokio::task::JoinHandle<()> {
        let server = self.clone();
        tokio::spawn(async move {
            if let Err(e) = server.start_health_check().await {
                error!("Failed to start health check server: {}", e);
            }
        })
    }

    /// Starts the secure gRPC server.
    ///
    /// This method sets up and runs the TLS-enabled gRPC server that hosts
    /// the external processor. It loads the TLS certificates, creates the
    /// service, and starts the server.
    ///
    /// # Arguments
    ///
    /// * `processor` - The external processor implementation to host
    ///
    /// # Returns
    ///
    /// A `Result` indicating success or failure
    async fn start_grpc<P: ExtProcessor + 'static>(
        &self,
        processor: P,
    ) -> Result<(), Box<dyn error::Error + Send + Sync>> {
        // Check if TLS server is enabled
        if !self.config.enable_tls {
            info!("TLS server is disabled");
            return Ok(());
        }

        // Check if certificate files exist using async I/O
        if !tokio::fs::try_exists(&self.config.cert_file).await.unwrap_or(false) {
            return Err(format!("Certificate file not found: {:?}", self.config.cert_file).into());
        }
        if !tokio::fs::try_exists(&self.config.key_file).await.unwrap_or(false) {
            return Err(format!("Key file not found: {:?}", self.config.key_file).into());
        }

        info!("Loading TLS certificates...");
        let cert = tokio::fs::read(&self.config.cert_file)
            .await
            .map_err(|e| format!("Failed to read certificate file: {}", e))?;
        let key = tokio::fs::read(&self.config.key_file)
            .await
            .map_err(|e| format!("Failed to read key file: {}", e))?;

        let identity = Identity::from_pem(cert, key);
        let addr = self
            .config
            .address
            .parse()
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

    /// Starts the plaintext gRPC server.
    ///
    /// This method sets up and runs the non-TLS gRPC server that hosts
    /// the external processor. It creates the service and starts the server.
    /// If plaintext server is disabled in the configuration, this method
    /// returns immediately without starting a server.
    ///
    /// # Arguments
    ///
    /// * `processor` - The external processor implementation to host
    ///
    /// # Returns
    ///
    /// A `Result` indicating success or failure
    async fn start_plaintext_grpc<P: ExtProcessor + 'static>(
        &self,
        processor: P,
    ) -> Result<(), Box<dyn error::Error + Send + Sync>> {
        if !self.config.enable_plaintext_server {
            info!("Plaintext server is disabled");
            return Ok(());
        }

        let plaintext_addr = self
            .config
            .plaintext_address
            .as_ref()
            .ok_or("Plaintext address not configured")?;
        let addr = plaintext_addr.parse()?;
        let service = ExtProcService::new(processor);

        info!("Starting plaintext gRPC server on {}", plaintext_addr);
        Server::builder()
            .add_service(service.into_server())
            .serve(addr)
            .await?;

        Ok(())
    }

    /// Starts the health check HTTP server.
    ///
    /// This method sets up and runs a simple HTTP server that responds to all
    /// requests with an empty 200 OK response. This can be used for health checking
    /// by load balancers or container orchestration systems.
    ///
    /// # Returns
    ///
    /// A `Result` indicating success or failure
    async fn start_health_check(&self) -> Result<(), Box<dyn error::Error + Send + Sync>> {
        let listener = TcpListener::bind(&self.config.health_check_address).await?;
        info!(
            "Starting health check server on {}",
            self.config.health_check_address
        );

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
