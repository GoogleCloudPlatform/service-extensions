use serde::Deserialize;
use std::path::PathBuf;

#[derive(Debug, Clone, Deserialize)]
pub struct ServerConfig {
    pub address: String,
    pub plaintext_address: Option<String>,
    pub health_check_address: Option<String>,
    pub cert_file: Option<PathBuf>,
    pub key_file: Option<PathBuf>,
    pub enable_plaintext_server: bool,
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            address: "0.0.0.0:443".to_string(),
            plaintext_address: Some("0.0.0.0:8080".to_string()),
            health_check_address: Some("0.0.0.0:80".to_string()),
            cert_file: Some(PathBuf::from("extproc/ssl_creds/localhost.crt")),
            key_file: Some(PathBuf::from("extproc/ssl_creds/localhost.key")),
            enable_plaintext_server: true,
        }
    }
}