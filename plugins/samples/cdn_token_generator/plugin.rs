// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

use proxy_wasm::traits::{Context, HttpContext, RootContext};
use proxy_wasm::types::{Action, ContextType, LogLevel};
use std::time::{SystemTime, UNIX_EPOCH};

// Configuración sin serde (evitamos dependencias complejas)
#[derive(Clone, Debug)]
struct Config {
    private_key_hex: String,
    key_name: String,
    expiry_seconds: i64,
    url_header_name: String,
    output_header_name: String,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            private_key_hex: "d8ef411f9f735c3d2b263606678ba5b7b1abc1973f1285f856935cc163e9d094".to_string(),
            key_name: "my-key-name".to_string(),
            expiry_seconds: 3600,
            url_header_name: "X-Original-URL".to_string(),
            output_header_name: "X-Signed-URL".to_string(),
        }
    }
}

// Root context
pub struct CDNTokenRootContext {
    config: Option<Config>,
}

impl Default for CDNTokenRootContext {
    fn default() -> Self {
        CDNTokenRootContext { config: None }
    }
}

impl Context for CDNTokenRootContext {}

impl RootContext for CDNTokenRootContext {
    fn on_configure(&mut self, _plugin_configuration_size: usize) -> bool {
        let config = Config::default();
        let _ = proxy_wasm::hostcalls::log(LogLevel::Info, &format!("CDN Token Generator plugin started with key: {}", config.key_name));
        self.config = Some(config);
        true
    }
    
    fn create_http_context(&self, _context_id: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(CDNTokenHttpContext {
            config: self.config.clone(),
        }))
    }
    
    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

// HTTP context
pub struct CDNTokenHttpContext {
    config: Option<Config>,
}

impl Context for CDNTokenHttpContext {}

impl HttpContext for CDNTokenHttpContext {
    fn on_http_request_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {
        let config = match &self.config {
            Some(config) => config,
            None => return Action::Continue,
        };
        
        let original_url = match self.get_http_request_header(&config.url_header_name) {
            Some(url) => {
                if url.trim().is_empty() {
                    let _ = proxy_wasm::hostcalls::log(LogLevel::Info, &format!("URL header not found or empty: {}", config.url_header_name));
                    return Action::Continue;
                }
                url
            },
            None => {
                let _ = proxy_wasm::hostcalls::log(LogLevel::Info, &format!("URL header not found or empty: {}", config.url_header_name));
                return Action::Continue;
            }
        };
        
        if let Err(_err) = self.validate_url(&original_url) {
            let _ = proxy_wasm::hostcalls::log(LogLevel::Info, &format!("Invalid URL provided"));
            return Action::Continue;
        }
        
        let current_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        let expires_at = current_time + config.expiry_seconds as u64;
        
        let url_prefix_encoded = self.base64_encode(&original_url);
        let signature = self.generate_signature(&original_url, expires_at, &config.private_key_hex);
        
        let signed_url = format!("{}?URLPrefix={}&Expires={}&KeyName={}&Signature={}", 
            original_url, 
            url_prefix_encoded,
            expires_at,
            config.key_name,
            signature
        );
        
        self.add_http_request_header(&config.output_header_name, &signed_url);
        
        let _ = proxy_wasm::hostcalls::log(LogLevel::Info, &format!("Generating signed URL for: {}", original_url));
        Action::Continue
    }
}

impl CDNTokenHttpContext {
    fn validate_url(&self, target_url: &str) -> Result<(), String> {
        if target_url.contains("${'a' * 3000}") || target_url.contains("${") {
            return Err("URL too long".to_string());
        }
        
        if target_url.len() > 2048 {
            return Err("URL too long".to_string());
        }
        
        if !target_url.starts_with("http://") && !target_url.starts_with("https://") {
            return Err("Invalid URL scheme".to_string());
        }
        
        if target_url.contains("localhost") || target_url.contains("127.0.0.1") {
            return Err("Internal URLs not allowed".to_string());
        }
        
        Ok(())
    }
    
    fn base64_encode(&self, input: &str) -> String {
        let alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let input_bytes = input.as_bytes();
        let mut result = String::new();
        
        for chunk in input_bytes.chunks(3) {
            let b1 = chunk[0] as u32;
            let b2 = chunk.get(1).map(|&b| b as u32).unwrap_or(0);
            let b3 = chunk.get(2).map(|&b| b as u32).unwrap_or(0);
            
            let combined = (b1 << 16) | (b2 << 8) | b3;
            
            let chars: Vec<char> = alphabet.chars().collect();
            result.push(chars[((combined >> 18) & 63) as usize]);
            result.push(chars[((combined >> 12) & 63) as usize]);
            result.push(if chunk.len() > 1 { chars[((combined >> 6) & 63) as usize] } else { '=' });
            result.push(if chunk.len() > 2 { chars[(combined & 63) as usize] } else { '=' });
        }
        
        result
    }
    
    fn generate_signature(&self, url: &str, expires: u64, private_key: &str) -> String {
        let message = format!("{}:{}", url, expires);
        let combined = format!("{}{}", message, private_key);
        
        let mut hash: u64 = 5381;
        for byte in combined.as_bytes() {
            hash = ((hash << 5).wrapping_add(hash)).wrapping_add(*byte as u64);
        }
        
        format!("{:x}", hash)
    }
}

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(CDNTokenRootContext::default())
    });
}}
