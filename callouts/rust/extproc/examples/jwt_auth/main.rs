// examples/jwt-auth/main.rs
use async_trait::async_trait;
use ext_proc::{
    processor::{ExtProcessor, ProcessingError},
    envoy::service::ext_proc::v3::{
        ProcessingRequest,
        ProcessingResponse,
        processing_request::Request as ProcessingRequestVariant,
        HttpHeaders,
    },
    server::{CalloutServer, Config},
    utils::mutations,
};
use jsonwebtoken::{decode, DecodingKey, Validation, Algorithm};
use log::{info, error};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

/// JWTAuthProcessor demonstrates JWT authentication
#[derive(Clone)]
struct JWTAuthProcessor {
    public_key: Vec<u8>,
}

#[derive(Debug, Serialize, Deserialize)]
struct Claims {
    sub: String,
    name: String,
    iat: i64,
    exp: i64,
    #[serde(flatten)]
    extra: HashMap<String, Value>,
}

impl JWTAuthProcessor {
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

    fn validate_jwt_token(&self, headers: &HttpHeaders) -> Result<HashMap<String, String>, String> {
        let token = self.extract_jwt_token(headers)?;

        let decoding_key = match DecodingKey::from_rsa_pem(&self.public_key) {
            Ok(key) => key,
            Err(e) => return Err(format!("Failed to parse public key: {}", e)),
        };

        let mut validation = Validation::new(Algorithm::RS256);
        validation.validate_exp = true; // For simplicity in the example

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
    async fn process_request_headers(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        if let Some(ProcessingRequestVariant::RequestHeaders(headers)) = &req.request {
            match self.validate_jwt_token(headers) {
                Ok(claims) => {
                    let headers_to_add: Vec<(String, String)> = claims
                        .into_iter()
                        .map(|(key, value)| (format!("decoded-{}", key), value))
                        .collect();

                    Ok(mutations::add_header_mutation(headers_to_add, vec![], true, true))
                },
                Err(e) => {
                    error!("JWT validation failed: {}", e);
                    Err(ProcessingError::PermissionDenied("Authorization token is invalid".to_string()))
                }
            }
        } else {
            // If no headers, just pass through
            Ok(ProcessingResponse::default())
        }
    }

    async fn process_response_headers(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    async fn process_request_body(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }

    async fn process_response_body(&self, _req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        Ok(ProcessingResponse::default())
    }
}

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
    use super::*;
    use ext_proc::envoy::{
        config::core::v3::{HeaderMap, HeaderValue},
        service::ext_proc::v3::{
            processing_response::Response as ProcessingResponseVariant,
        },
    };
    use jsonwebtoken::{encode, EncodingKey, Header};
    use std::collections::HashMap;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

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

    fn generate_test_jwt_token(private_key: &[u8], claims: Claims) -> Result<String, jsonwebtoken::errors::Error> {
        let encoding_key = EncodingKey::from_rsa_pem(private_key)?;
        encode(&Header::new(Algorithm::RS256), &claims, &encoding_key)
    }

    fn get_current_timestamp() -> i64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("Time went backwards")
            .as_secs() as i64
    }

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
        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Check if the response contains the expected headers
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.as_ref().unwrap().header_mutation.as_ref().unwrap();

            // Check if all expected headers are present
            let mut found_sub = false;
            let mut found_name = false;
            let mut found_iat = false;
            let mut found_exp = false;

            for header in &header_mutation.set_headers {
                match header.header.as_ref().unwrap().key.as_str() {
                    "decoded-sub" => {
                        found_sub = true;
                        assert_eq!(String::from_utf8_lossy(&header.header.as_ref().unwrap().raw_value), "1234567890");
                    },
                    "decoded-name" => {
                        found_name = true;
                        assert_eq!(String::from_utf8_lossy(&header.header.as_ref().unwrap().raw_value), "John Doe");
                    },
                    "decoded-iat" => {
                        found_iat = true;
                    },
                    "decoded-exp" => {
                        found_exp = true;
                    },
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
        extra.insert("permissions".to_string(), Value::Array(vec![
            Value::String("read".to_string()),
            Value::String("write".to_string())
        ]));

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
        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers");

        // Check if the response contains the expected headers
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.as_ref().unwrap().header_mutation.as_ref().unwrap();

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
                    },
                    "decoded-name" => {
                        found_name = true;
                        assert_eq!(value, "Jane Smith");
                    },
                    "decoded-role" => {
                        found_role = true;
                        assert_eq!(value, "admin");
                    },
                    "decoded-org" => {
                        found_org = true;
                        assert_eq!(value, "example-org");
                    },
                    "decoded-permissions" => {
                        found_permissions = true;
                        assert!(value.contains("read"));
                        assert!(value.contains("write"));
                    },
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
            assert!(msg.contains("invalid") || msg.contains("expired"),
                    "Error message should indicate token is invalid or expired");
        } else {
            panic!("Expected PermissionDenied error");
        }
    }

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

        assert!(result.is_err(), "Expected error for missing authorization header");
        if let Err(ProcessingError::PermissionDenied(msg)) = result {
            assert!(msg.contains("Authorization token is invalid"),
                    "Error message should indicate token is invalid");
        } else {
            panic!("Expected PermissionDenied error");
        }
    }

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
            assert!(msg.contains("invalid"), "Error message should indicate token is invalid");
        } else {
            panic!("Expected PermissionDenied error");
        }
    }

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
        let response = processor.process_request_headers(&request).await
            .expect("Failed to process request headers without Bearer prefix");

        // Verify we got a valid response with decoded claims
        if let Some(ProcessingResponseVariant::RequestHeaders(headers_response)) = response.response {
            let header_mutation = headers_response.response.as_ref().unwrap().header_mutation.as_ref().unwrap();

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
            request: Some(ProcessingRequestVariant::ResponseHeaders(HttpHeaders::default())),
            ..Default::default()
        };

        // Create processor with test public key
        let processor = JWTAuthProcessor { public_key };

        // Process the request - should return default response
        let response = processor.process_request_headers(&request).await
            .expect("Failed to process non-request headers");

        // Should get default response
        assert_eq!(response, ProcessingResponse::default());
    }

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
        let response = processor.process_response_headers(&empty_request).await
            .expect("Failed to process response headers");
        assert_eq!(response, ProcessingResponse::default());

        // Test request body method
        let response = processor.process_request_body(&empty_request).await
            .expect("Failed to process request body");
        assert_eq!(response, ProcessingResponse::default());

        // Test response body method
        let response = processor.process_response_body(&empty_request).await
            .expect("Failed to process response body");
        assert_eq!(response, ProcessingResponse::default());
    }
}