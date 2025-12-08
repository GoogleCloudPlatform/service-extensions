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
    pub enable_tls: bool,
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
            enable_tls: false,
        }
    }
}