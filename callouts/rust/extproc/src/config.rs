use serde::Deserialize;
use std::path::PathBuf;

#[derive(Debug, Clone, Deserialize)]
pub struct ServerConfig {
    pub address: String,
    pub insecure_address: Option<String>,
    pub health_check_address: Option<String>,
    pub cert_file: Option<PathBuf>,
    pub key_file: Option<PathBuf>,
    pub enable_insecure_server: bool,
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            address: "0.0.0.0:8443".to_string(),
            insecure_address: Some("0.0.0.0:8080".to_string()),
            health_check_address: Some("0.0.0.0:8000".to_string()),
            cert_file: Some(PathBuf::from("extproc/certs/localhost.crt")),
            key_file: Some(PathBuf::from("extproc/certs/localhost.key")),
            enable_insecure_server: true,
        }
    }
}