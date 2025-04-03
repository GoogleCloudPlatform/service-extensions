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
//! # JWT Authentication Example
//!
//! This module demonstrates how to create an Envoy external processor that
//! validates JWT tokens in request headers and adds decoded claims as new headers.
//!
//! ## Overview
//!
//! The `JWTAuthProcessor` implements the `ExtProcessor` trait to:
//!
//! 1. Extract JWT tokens from the "Authorization" header
//! 2. Validate tokens using RSA public key cryptography
//! 3. Decode token claims and add them as new headers with "decoded-" prefix
//! 4. Reject requests with invalid or expired tokens
//!
//! This example shows how to implement authentication and authorization in an
//! Envoy external processor using industry-standard JWT tokens.
//!
//! ## Usage
//!
//! To run this example:
//!
//! ```bash
//! cargo run --example jwt_auth [path/to/public_key.pem]
//! ```
//!
//! If no path is provided, it defaults to "extproc/ssl_creds/publickey.pem".

use async_trait::async_trait;
use ext_proc::{
    envoy::service::ext_proc::v3::{
        processing_request::Request as ProcessingRequestVariant, HttpHeaders, ProcessingRequest,
        ProcessingResponse,
    },
    processor::{ExtProcessor, ProcessingError},
    server::{CalloutServer, Config},
    utils::mutations,
};
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use log::error;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::fs;

/// `JWTAuthProcessor` validates JWT tokens in request headers and adds decoded claims as new headers.
///
/// This processor:
/// - Extracts JWT tokens from the "Authorization" header
/// - Validates tokens using RSA public key cryptography
/// - Decodes token claims and adds them as new headers with "decoded-" prefix
/// - Rejects requests with invalid or expired tokens
#[derive(Clone)]
struct JWTAuthProcessor {
    /// The RSA public key used to validate JWT tokens
    public_key: Vec<u8>,
}

/// JWT claims structure for token validation and extraction.
///
/// This structure defines the expected format of JWT claims:
/// - Standard claims (sub, name, iat, exp)
/// - Custom claims (stored in the `extra` field)
#[derive(Debug, Serialize, Deserialize)]
struct Claims {
    /// Subject identifier (usually a user ID)
    sub: String,

    /// User's name or identifier
    name: String,

    /// Issued at timestamp (seconds since Unix epoch)
    iat: i64,

    /// Expiration timestamp (seconds since Unix epoch)
    exp: i64,

    /// Additional custom claims as key-value pairs
    #[serde(flatten)]
    extra: HashMap<String, Value>,
}

impl JWTAuthProcessor {
    /// Creates a new `JWTAuthProcessor` with the specified public key.
    ///
    /// # Arguments
    ///
    /// * `key_path` - Path to the RSA public key file in PEM format
    ///
    /// # Returns
    ///
    /// A new `JWTAuthProcessor` instance
    ///
    /// # Panics
    ///
    /// Panics if the public key file cannot be read
    fn new(key_path: &str) -> Self {
        let public_key = match fs::read(key_path) {
            Ok(key) => key,
            Err(e) => {
                error!("Failed to load public key from {}: {}", key_path, e);
                panic!("Failed to load public key");
            }
        };

        Self { public_key }
    }

    /// Extracts the JWT token from the request headers.
    ///
    /// Looks for an "Authorization" header and extracts the token,
    /// handling both "Bearer TOKEN" format and raw token format.
    ///
    /// # Arguments
    ///
    /// * `headers` - The HTTP headers from the request
    ///
    /// # Returns
    ///
    /// * `Ok(String)` - The extracted JWT token
    /// * `Err(String)` - Error message if no Authorization header is found
    fn extract_jwt_token(&self, headers: &HttpHeaders) -> Result<String, String> {
        for header in &headers.headers.as_ref().unwrap().headers {
            if header.key == "Authorization" {
                let auth_value = String::from_utf8_lossy(&header.raw_value);
                let token = if auth_value.starts_with("Bearer ") {
                    auth_value.trim_start_matches("Bearer ").to_string()
                } else {
                    auth_value.to_string()
                };
                return Ok(token);
            }
        }

        Err("No Authorization header found".to_string())
    }

    /// Validates and decodes a JWT token from the request headers.
    ///
    /// This method:
    /// 1. Extracts the token from headers
    /// 2. Validates the token signature using the RSA public key
    /// 3. Checks token expiration
    /// 4. Extracts all claims (standard and custom)
    ///
    /// # Arguments
    ///
    /// * `headers` - The HTTP headers from the request
    ///
    /// # Returns
    ///
    /// * `Ok(HashMap<String, String>)` - Map of claim names to values
    /// * `Err(String)` - Error message if validation fails
    fn validate_jwt_token(&self, headers: &HttpHeaders) -> Result<HashMap<String, String>, String> {
        let token = self.extract_jwt_token(headers)?;

        let decoding_key = match DecodingKey::from_rsa_pem(&self.public_key) {
            Ok(key) => key,
            Err(e) => return Err(format!("Failed to parse public key: {}", e)),
        };

        let mut validation = Validation::new(Algorithm::RS256);
        validation.validate_exp = true;

        let token_data = match decode::<Claims>(&token, &decoding_key, &validation) {
            Ok(data) => data,
            Err(e) => return Err(format!("Invalid token: {}", e)),
        };

        let claims = token_data.claims;
        let mut decoded_claims = HashMap::new();

        // Add standard claims
        decoded_claims.insert("sub".to_string(), claims.sub);
        decoded_claims.insert("name".to_string(), claims.name);
        decoded_claims.insert("iat".to_string(), claims.iat.to_string());
        decoded_claims.insert("exp".to_string(), claims.exp.to_string());

        // Add any extra claims
        for (key, value) in claims.extra {
            decoded_claims.insert(key, value.to_string().trim_matches('"').to_string());
        }

        Ok(decoded_claims)
    }
}

#[async_trait]
impl ExtProcessor for JWTAuthProcessor {
    /// Processes request headers to validate JWT tokens and add decoded claims.
    ///
    /// If a valid JWT token is found in the "Authorization" header:
    /// - Extracts and validates the token
    /// - Adds all decoded claims as new headers with "decoded-" prefix
    /// - Clears the route cache to ensure the new headers are considered for routing
    ///
    /// If the token is invalid or expired, returns a permission denied error.
    ///
    /// # Arguments
    ///
    /// * `req` - The processing request containing request headers
    ///
    /// # Returns
    ///
    /// * `Ok(ProcessingResponse)` - Response with added claim headers
    /// * `Err(ProcessingError)` - Permission denied error for invalid tokens
    async fn process_request_headers(
        &self,
        req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        if let Some(ProcessingRequestVariant::RequestHeaders(headers)) = &req.request {
            match self.validate_jwt_token(headers) {
                Ok(claims) => {
                    let headers_to_add: Vec<(String, String)> = claims
                        .into_iter()
                        .map(|(key, value)| (format!("decoded-{}", key), value))
                        .collect();

                    Ok(mutations::add_header_mutation(
                        headers_to_add,
                        vec![],
                        true,
                        true,
                        None,
                    ))
                }
                Err(e) => {
                    error!("JWT validation failed: {}", e);
                    Err(ProcessingError::PermissionDenied(
                        "Authorization token is invalid".to_string(),
                    ))
                }
            }
        } else {
            // If no headers, just pass through
            Ok(ProcessingResponse::default())
        }
    }

    /// Processes response headers.
    ///
    /// This implementation simply passes through response headers without modification.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing response headers
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the response headers to proceed unchanged.
    async fn process_response_headers(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    /// Processes request bodies.
    ///
    /// This implementation simply passes through request bodies without modification.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing the request body
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the request body to proceed unchanged.
    async fn process_request_body(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    /// Processes response bodies.
    ///
    /// This implementation simply passes through response bodies without modification.
    ///
    /// # Arguments
    ///
    /// * `_req` - The processing request containing the response body
    ///
    /// # Returns
    ///
    /// A default `ProcessingResponse` that allows the response body to proceed unchanged.
    async fn process_response_body(
        &self,
        _req: &ProcessingRequest,
    ) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }
}

/// Main entry point for the JWT authentication example.
///
/// Sets up and starts the external processor server with the `JWTAuthProcessor`.
/// Accepts an optional command-line argument for the path to the public key file.
///
/// # Returns
///
/// A Result indicating success or failure of the server startup.
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();

    // Get the public key path from command line arguments or use default
    let args: Vec<String> = std::env::args().collect();
    let key_path = if args.len() > 1 {
        &args[1]
    } else {
        "extproc/ssl_creds/publickey.pem"
    };

    // Using default config
    let config = Config::default();

    let server = CalloutServer::new(config);
    let processor = JWTAuthProcessor::new(key_path);

    // Start all services
    let secure = server.spawn_grpc(processor.clone()).await;
    let plaintext = server.spawn_plaintext_grpc(processor.clone()).await;
    let health = server.spawn_health_check().await;

    // Wait for all services
    let _ = tokio::try_join!(secure, plaintext, health)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    //! Test module for the `JWTAuthProcessor`.
    //!
    //! Contains comprehensive tests for JWT token validation and claim extraction,
    //! including:
    //! - Valid token validation
    //! - Custom claim extraction
    //! - Expired token rejection
    //! - Missing authorization header handling
    //! - Invalid token format rejection
    //! - Token without Bearer prefix handling
    //! - Non-request headers input handling
    //! - Other processor methods behavior

    use super::*;
    use ext_proc::envoy::{
        config::core::v3::{HeaderMap, HeaderValue},
        service::ext_proc::v3::processing_response::Response as ProcessingResponseVariant,
    };
    use jsonwebtoken::{encode, EncodingKey, Header};
    use std::collections::HashMap;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    /// Creates test HTTP headers with an optional JWT token.
    ///
    /// # Arguments
    ///
    /// * `token` - Optional JWT token to include in the Authorization header
    ///
    /// # Returns
    ///
    /// An `HttpHeaders` object with standard headers and optional Authorization header
    fn create_test_headers(token: Option<&str>) -> HttpHeaders {
        let mut headers = vec![];

        if let Some(token) = token {
            headers.push(HeaderValue {
                key: "Authorization".to_string(),
                raw_value: format!("Bearer {}", token).into_bytes(),
                ..Default::default()
            });
        }

        // Add some standard headers
        headers.push(HeaderValue {
            key: "Host".to_string(),
            raw_value: b"example.com".to_vec(),
            ..Default::default()
        });

        headers.push(HeaderValue {
            key: "User-Agent".to_string(),
            raw_value: b"test-client".to_vec(),
            ..Default::default()
        });

        HttpHeaders {
            headers: Some(HeaderMap {
                headers,
                ..Default::default()
            }),
            ..Default::default()
        }
    }

    /// Generates a test JWT token with the given claims.
    ///
    /// # Arguments
    ///
    /// * `private_key` - RSA private key in PEM format
    /// * `claims` - Claims to include in the token
    ///
    /// # Returns
    ///
    /// A Result containing the JWT token string or an error
    fn generate_test_jwt_token(
        private_key: &[u8],
        claims: Claims,
    ) -> Result<String, jsonwebtoken::errors::Error> {
        let encoding_key = EncodingKey::from_rsa_pem(private_key)?;
        encode(&Header::new(Algorithm::RS256), &claims, &encoding_key)
    }

    /// Gets the current Unix timestamp.
    ///
    /// # Returns
    ///
    /// Current time as seconds since Unix epoch
    fn get_current_timestamp() -> i64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("Time went backwards")
            .as_secs() as i64
    }

    /// Loads test RSA keys from various possible locations.
    ///
    /// # Returns
    ///
    /// An Option containing a tuple of (private_key, public_key) if found
    fn load_test_keys() -> Option<(Vec<u8>, Vec<u8>)> {
        // Try different paths for the test keys
        let possible_private_key_paths = [
            "../../ssl_creds/localhost.key",
            "ssl_creds/localhost.key",
            "extproc/ssl_creds/localhost.key",
        ];

        let possible_public_key_paths = [
            "../../ssl_creds/publickey.pem",
            "ssl_creds/publickey.pem",
            "extproc/ssl_creds/publickey.pem",
        ];

        for private_path in &possible_private_key_paths {
            if let Ok(private_key) = fs::read(private_path) {
                for public_path in &possible_public_key_paths {
                    if let Ok(public_key) = fs::read(public_path) {
                        return Some((private_key, public_key));
                    }
                }
            }
        }

        None
    }

    /// Tests validation of a valid JWT token.
    ///
    /// This test verifies that:
    /// - A valid token is properly validated
    /// - Standard claims (sub, name, iat, exp) are extracted
    /// - Claims are added as headers with "decoded-" prefix
    #[tokio::test]
    async fn test_valid_token() {
        // Load test keys
        let (private_key, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        // Create test claims
        let now = get_current_timestamp();
        let claims = Claims {
            sub: "1234567890".to_string(),
            name: "John Doe".to_string(),
            iat: now,
            exp: now + 3600, // Valid for 1 hour
            extra: HashMap::new(),
        };

        // Generate JWT token
        let token = match generate_test_jwt_token(&private_key, claims) {
            Ok(token) => token,
            Err(e) => {
                panic!("Failed to generate test JWT token: {}", e);
            }
        };

        // Create headers with the token
        let headers = create_test_headers(Some(&token));

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(headers)),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request
        let response = processor
            .process_request_headers(&request)
            .await
            .expect("Failed to process request headers");

        // Check if the response contains the expected headers
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check if all expected headers are present
            let mut found_sub = false;
            let mut found_name = false;
            let mut found_iat = false;
            let mut found_exp = false;

            for header in &header_mutation.set_headers {
                match header.header.as_ref().unwrap().key.as_str() {
                    "decoded-sub" => {
                        found_sub = true;
                        assert_eq!(
                            String::from_utf8_lossy(&header.header.as_ref().unwrap().raw_value),
                            "1234567890"
                        );
                    }
                    "decoded-name" => {
                        found_name = true;
                        assert_eq!(
                            String::from_utf8_lossy(&header.header.as_ref().unwrap().raw_value),
                            "John Doe"
                        );
                    }
                    "decoded-iat" => {
                        found_iat = true;
                    }
                    "decoded-exp" => {
                        found_exp = true;
                    }
                    _ => {}
                }
            }

            assert!(found_sub, "decoded-sub header not found");
            assert!(found_name, "decoded-name header not found");
            assert!(found_iat, "decoded-iat header not found");
            assert!(found_exp, "decoded-exp header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests extraction of custom claims from a JWT token.
    ///
    /// This test verifies that:
    /// - Custom claims beyond the standard ones are properly extracted
    /// - Complex claim types (strings, arrays) are handled correctly
    /// - All claims are added as headers with "decoded-" prefix
    #[tokio::test]
    async fn test_token_with_custom_claims() {
        // Load test keys
        let (private_key, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        // Create test claims with extra fields
        let now = get_current_timestamp();
        let mut extra = HashMap::new();
        extra.insert("role".to_string(), Value::String("admin".to_string()));
        extra.insert("org".to_string(), Value::String("example-org".to_string()));
        extra.insert(
            "permissions".to_string(),
            Value::Array(vec![
                Value::String("read".to_string()),
                Value::String("write".to_string()),
            ]),
        );

        let claims = Claims {
            sub: "user123".to_string(),
            name: "Jane Smith".to_string(),
            iat: now,
            exp: now + 3600,
            extra,
        };

        // Generate JWT token
        let token = match generate_test_jwt_token(&private_key, claims) {
            Ok(token) => token,
            Err(e) => {
                panic!("Failed to generate test JWT token: {}", e);
            }
        };

        // Create headers with the token
        let headers = create_test_headers(Some(&token));

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(headers)),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request
        let response = processor
            .process_request_headers(&request)
            .await
            .expect("Failed to process request headers");

        // Check if the response contains the expected headers
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check if all expected headers are present
            let mut found_sub = false;
            let mut found_name = false;
            let mut found_role = false;
            let mut found_org = false;
            let mut found_permissions = false;

            for header in &header_mutation.set_headers {
                let key = &header.header.as_ref().unwrap().key;
                let value = String::from_utf8_lossy(&header.header.as_ref().unwrap().raw_value);

                match key.as_str() {
                    "decoded-sub" => {
                        found_sub = true;
                        assert_eq!(value, "user123");
                    }
                    "decoded-name" => {
                        found_name = true;
                        assert_eq!(value, "Jane Smith");
                    }
                    "decoded-role" => {
                        found_role = true;
                        assert_eq!(value, "admin");
                    }
                    "decoded-org" => {
                        found_org = true;
                        assert_eq!(value, "example-org");
                    }
                    "decoded-permissions" => {
                        found_permissions = true;
                        assert!(value.contains("read"));
                        assert!(value.contains("write"));
                    }
                    _ => {}
                }
            }

            assert!(found_sub, "decoded-sub header not found");
            assert!(found_name, "decoded-name header not found");
            assert!(found_role, "decoded-role header not found");
            assert!(found_org, "decoded-org header not found");
            assert!(found_permissions, "decoded-permissions header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests rejection of an expired JWT token.
    ///
    /// This test verifies that:
    /// - An expired token is properly rejected
    /// - A PermissionDenied error is returned
    /// - The error message indicates the token is invalid or expired
    #[tokio::test]
    async fn test_expired_token() {
        // Load test keys
        let (private_key, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        // Create expired claims
        let now = get_current_timestamp();
        let claims = Claims {
            sub: "expired_user".to_string(),
            name: "Expired User".to_string(),
            iat: now - 7200, // 2 hours ago
            exp: now - 3600, // Expired 1 hour ago
            extra: HashMap::new(),
        };

        // Generate JWT token
        let token = match generate_test_jwt_token(&private_key, claims) {
            Ok(token) => token,
            Err(e) => {
                panic!("Failed to generate test JWT token: {}", e);
            }
        };

        // Create headers with the token
        let headers = create_test_headers(Some(&token));

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(headers)),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request - should fail with expired token
        let result = processor.process_request_headers(&request).await;

        assert!(result.is_err(), "Expected error for expired token");
        if let Err(ProcessingError::PermissionDenied(msg)) = result {
            assert!(
                msg.contains("invalid") || msg.contains("expired"),
                "Error message should indicate token is invalid or expired"
            );
        } else {
            panic!("Expected PermissionDenied error");
        }
    }

    /// Tests handling of requests with missing Authorization header.
    ///
    /// This test verifies that:
    /// - Requests without an Authorization header are rejected
    /// - A PermissionDenied error is returned
    /// - The error message indicates the token is invalid
    #[tokio::test]
    async fn test_missing_authorization_header() {
        // Load test keys
        let (_, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        // Create headers without token
        let headers = create_test_headers(None);

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(headers)),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request - should fail with missing authorization header
        let result = processor.process_request_headers(&request).await;

        assert!(
            result.is_err(),
            "Expected error for missing authorization header"
        );
        if let Err(ProcessingError::PermissionDenied(msg)) = result {
            assert!(
                msg.contains("Authorization token is invalid"),
                "Error message should indicate token is invalid"
            );
        } else {
            panic!("Expected PermissionDenied error");
        }
    }

    /// Tests rejection of malformed JWT tokens.
    ///
    /// This test verifies that:
    /// - Tokens with invalid format are rejected
    /// - A PermissionDenied error is returned
    /// - The error message indicates the token is invalid
    #[tokio::test]
    async fn test_invalid_token_format() {
        // Load test keys
        let (_, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        // Create headers with invalid token
        let headers = create_test_headers(Some("invalid.token.format"));

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(headers)),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request - should fail with invalid token
        let result = processor.process_request_headers(&request).await;

        assert!(result.is_err(), "Expected error for invalid token format");
        if let Err(ProcessingError::PermissionDenied(msg)) = result {
            assert!(
                msg.contains("invalid"),
                "Error message should indicate token is invalid"
            );
        } else {
            panic!("Expected PermissionDenied error");
        }
    }

    /// Tests handling of tokens without the "Bearer " prefix.
    ///
    /// This test verifies that:
    /// - Tokens provided directly in the Authorization header (without "Bearer " prefix) are accepted
    /// - Claims are still properly extracted and added as headers
    #[tokio::test]
    async fn test_token_without_bearer_prefix() {
        // Load test keys
        let (private_key, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        // Create test claims
        let now = get_current_timestamp();
        let claims = Claims {
            sub: "1234567890".to_string(),
            name: "John Doe".to_string(),
            iat: now,
            exp: now + 3600,
            extra: HashMap::new(),
        };

        // Generate JWT token
        let token = match generate_test_jwt_token(&private_key, claims) {
            Ok(token) => token,
            Err(e) => {
                panic!("Failed to generate test JWT token: {}", e);
            }
        };

        // Create headers with token but without "Bearer " prefix
        let auth_header = HeaderValue {
            key: "Authorization".to_string(),
            raw_value: token.clone().into_bytes(), // No "Bearer " prefix
            ..Default::default()
        };

        let headers = HttpHeaders {
            headers: Some(HeaderMap {
                headers: vec![
                    auth_header,
                    HeaderValue {
                        key: "Host".to_string(),
                        raw_value: b"example.com".to_vec(),
                        ..Default::default()
                    },
                ],
                ..Default::default()
            }),
            ..Default::default()
        };

        // Create request with headers
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::RequestHeaders(headers)),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request - should still work without "Bearer " prefix
        let response = processor
            .process_request_headers(&request)
            .await
            .expect("Failed to process request headers without Bearer prefix");

        // Verify we got a valid response with decoded claims
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response
        {
            let header_mutation = headers_response
                .response
                .as_ref()
                .unwrap()
                .header_mutation
                .as_ref()
                .unwrap();

            // Check if sub claim is present
            let mut found_sub = false;
            for header in &header_mutation.set_headers {
                if header.header.as_ref().unwrap().key == "decoded-sub" {
                    found_sub = true;
                    break;
                }
            }

            assert!(found_sub, "decoded-sub header not found");
        } else {
            panic!("Unexpected response type");
        }
    }

    /// Tests handling of non-request headers input.
    ///
    /// This test verifies that:
    /// - When the processor receives something other than request headers, it returns a default response
    /// - No error is thrown for unexpected input types
    #[tokio::test]
    async fn test_non_request_headers_input() {
        // Load test keys
        let (_, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        // Create a request with something other than RequestHeaders
        let request = ProcessingRequest {
            request: Some(ProcessingRequestVariant::ResponseHeaders(
                HttpHeaders::default(),
            )),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request - should return default response
        let response = processor
            .process_request_headers(&request)
            .await
            .expect("Failed to process non-request headers");

        // Should get default response
        assert_eq!(response, ProcessingResponse::default());
    }

    /// Tests the other processor methods that should pass through unchanged.
    ///
    /// This test verifies that:
    /// - The response_headers, request_body, and response_body methods all return default responses
    /// - These methods don't modify the traffic in any way
    #[tokio::test]
    async fn test_other_processor_methods() {
        // Load test keys
        let (_, public_key) = match load_test_keys() {
            Some(keys) => keys,
            None => {
                println!("Test keys not found, skipping test");
                return;
            }
        };

        let processor = JWTAuthProcessor { public_key };
        let empty_request = ProcessingRequest::default();

        // Test response headers method
        let response = processor
            .process_response_headers(&empty_request)
            .await
            .expect("Failed to process response headers");
        assert_eq!(response, ProcessingResponse::default());

        // Test request body method
        let response = processor
            .process_request_body(&empty_request)
            .await
            .expect("Failed to process request body");
        assert_eq!(response, ProcessingResponse::default());

        // Test response body method
        let response = processor
            .process_response_body(&empty_request)
            .await
            .expect("Failed to process response body");
        assert_eq!(response, ProcessingResponse::default());
    }
}
