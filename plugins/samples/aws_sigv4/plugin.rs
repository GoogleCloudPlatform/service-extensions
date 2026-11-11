// Copyright 2026 Google LLC
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

// [START serviceextensions_plugin_aws_sigv4]
use log::warn;
use hmac::{Hmac, Mac};
use p256::ecdsa::signature::DigestSigner;
use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::rc::Rc;

type HmacSha256 = Hmac<Sha256>;

proxy_wasm::main! {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {
        Box::new(MyRootContext {
            config: Rc::new(AwsSignerConfig::default()),
        })
    });
}}

// ── Config ────────────────────────────────────────────────────────────────────

#[derive(Deserialize, Debug, Clone, PartialEq, Default)]
#[serde(rename_all = "lowercase")]
enum SignatureType {
    #[default]
    V4,
    V4a,
}

#[derive(Deserialize, Debug, Clone, Default)]
struct AwsSignerConfig {
    access_key:     String,
    secret_key:     String,
    region:         String,
    service:        String,
    #[serde(default)]
    signature_type: SignatureType,
    
    #[serde(skip)]
    v4_hmac_key:    Vec<u8>,
    #[serde(skip)]
    v4a_hmac_key:   Vec<u8>,
}

// ── RootContext ───────────────────────────────────────────────────────────────

struct MyRootContext {
    config: Rc<AwsSignerConfig>,
}

impl Context for MyRootContext {}

impl RootContext for MyRootContext {
    fn on_configure(&mut self, _: usize) -> bool {
        if let Some(bytes) = self.get_plugin_configuration() {
            let s = match String::from_utf8(bytes) {
                Ok(v) => v,
                Err(e) => {
                    warn!("aws_sigv4: plugin config is not valid UTF-8: {}", e);
                    return false;
                }
            };
            match serde_json::from_str::<AwsSignerConfig>(&s) {
                Ok(mut cfg) => {
                    cfg.v4_hmac_key = format!("AWS4{}", cfg.secret_key).into_bytes();
                    cfg.v4a_hmac_key = format!("AWS4A{}", cfg.secret_key).into_bytes();
                    self.config = Rc::new(cfg);
                }
                Err(e) => {
                    warn!("aws_sigv4: plugin config is not valid JSON: {}", e);
                    return false;
                }
            }
        }
        true
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyHttpContext {
            config: self.config.clone(),
        }))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

// ── HttpContext ───────────────────────────────────────────────────────────────

struct MyHttpContext {
    config: Rc<AwsSignerConfig>,
}

impl Context for MyHttpContext {}

impl HttpContext for MyHttpContext {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        let cfg = self.config.clone();
        let now = self.get_current_time();
        let time_ns = now.duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as u64;
        let (date_str, datetime_str) = format_aws_datetime(time_ns);

        self.set_http_request_header("x-amz-date", Some(&datetime_str));
        if cfg.signature_type == SignatureType::V4a {
            self.set_http_request_header("x-amz-region-set", Some(&cfg.region));
        }

        let headers = self.get_http_request_headers();
        let method    = pseudo(&headers, ":method").unwrap_or("GET");
        let full_path = pseudo(&headers, ":path").unwrap_or("/");
        let (uri_path, query_str) = split_path_query(full_path);

        let payload_hash = if request_has_body(method, &headers) {
            if cfg.service.eq_ignore_ascii_case("s3") {
                "UNSIGNED-PAYLOAD".to_string()
            } else {
                warn!("aws_sigv4: Body detected for non-S3 service. Signing as empty.");
                sha256_hex(b"")
            }
        } else {
            sha256_hex(b"")
        };

        self.finalize_and_sign(
            payload_hash, &cfg, &date_str, &datetime_str,
            method, &uri_path, &query_str, &headers
        );

        Action::Continue
    }

    fn on_http_request_body(&mut self, _: usize, _: bool) -> Action {
        Action::Continue
    }
}

impl MyHttpContext {
    fn finalize_and_sign(
        &mut self,
        payload_hash: String,
        cfg: &AwsSignerConfig,
        date_str: &str,
        datetime_str: &str,
        method: &str,
        uri_path: &str,
        query_str: &str,
        headers: &[(String, String)],
    ) {
        if cfg.access_key.is_empty() || cfg.secret_key.is_empty() {
            warn!("aws_sigv4: access_key or secret_key is empty — skipping signing");
            return;
        }

        let (canonical_hdrs, signed_hdrs) = build_canonical_headers(headers);

        self.set_http_request_header("x-amz-content-sha256", Some(&payload_hash));

        let auth = match cfg.signature_type {
            SignatureType::V4 => sign_v4(
                method, uri_path, query_str,
                &canonical_hdrs, &signed_hdrs,
                datetime_str, date_str,
                &payload_hash, cfg,
            ),
            SignatureType::V4a => sign_v4a(
                method, uri_path, query_str,
                &canonical_hdrs, &signed_hdrs,
                datetime_str, date_str,
                &payload_hash, cfg,
            ),
        };

        match auth {
            Some(v) => self.set_http_request_header("Authorization", Some(&v)),
            None => warn!("aws_sigv4: signing failed — request will proceed without Authorization"),
        }
    }
}

// ── Header utilities ──────────────────────────────────────────────────────────

fn pseudo<'a>(headers: &'a [(String, String)], name: &str) -> Option<&'a str> {
    headers.iter().find(|(k, _)| k == name).map(|(_, v)| v.as_str())
}

fn split_path_query(path_and_query: &str) -> (String, String) {
    match path_and_query.split_once('?') {
        Some((p, q)) => (p.to_string(), q.to_string()),
        None => (path_and_query.to_string(), String::new()),
    }
}

fn request_has_body(method: &str, headers: &[(String, String)]) -> bool {
    match method {
        "GET" | "HEAD" | "OPTIONS" | "TRACE" => return false,
        _ => {}
    }
    let content_length: u64 = headers
        .iter()
        .find(|(k, _)| k.eq_ignore_ascii_case("content-length"))
        .and_then(|(_, v)| v.trim().parse().ok())
        .unwrap_or(0);
    let has_transfer_encoding = headers
        .iter()
        .any(|(k, v)| k.eq_ignore_ascii_case("transfer-encoding") && !v.trim().is_empty());
    content_length > 0 || has_transfer_encoding
}

fn build_canonical_headers(headers: &[(String, String)]) -> (String, String) {
    let mut map: BTreeMap<String, String> = BTreeMap::new();

    for (name, value) in headers {
        let lower = name.to_lowercase();
        
        let mut trimmed = String::with_capacity(value.len());
        for (i, word) in value.split_whitespace().enumerate() {
            if i > 0 { trimmed.push(' '); }
            trimmed.push_str(word);
        }

        match lower.as_str() {
            ":method" | ":path" | ":scheme"
            | "x-forwarded-for" | "x-forwarded-proto" | "x-forwarded-host"
            | "x-request-id" | "x-envoy-expected-rq-timeout-ms"
            | "x-envoy-original-path" => {}
            ":authority" => {
                map.entry("host".into()).or_insert(trimmed);
            }
            _ if !lower.starts_with(':') => {
                map.entry(lower)
                    .and_modify(|existing| {
                        existing.push(',');
                        existing.push_str(&trimmed);
                    })
                    .or_insert(trimmed);
            }
            _ => {}
        }
    }

    let canonical = map.iter().map(|(k, v)| format!("{}:{}\n", k, v)).collect();
    let signed    = map.keys().cloned().collect::<Vec<_>>().join(";");
    (canonical, signed)
}

// ── SigV4 ─────────────────────────────────────────────────────────────────────

fn sign_v4(
    method: &str,
    uri_path: &str,
    query_str: &str,
    canonical_hdrs: &str,
    signed_hdrs: &str,
    datetime_str: &str,
    date_str: &str,
    payload_hash: &str,
    cfg: &AwsSignerConfig,
) -> Option<String> {
    const ALGORITHM: &str = "AWS4-HMAC-SHA256";

    let canonical_request = [
        method,
        &uri_encode_path(uri_path),
        &canonical_query_string(query_str),
        canonical_hdrs,
        signed_hdrs,
        payload_hash,
    ]
    .join("\n");

    let credential_scope =
        format!("{}/{}/{}/aws4_request", date_str, cfg.region, cfg.service);

    let string_to_sign = format!(
        "{}\n{}\n{}\n{}",
        ALGORITHM,
        datetime_str,
        credential_scope,
        sha256_hex(canonical_request.as_bytes()),
    );

    let signing_key =
        derive_v4_signing_key(&cfg.v4_hmac_key, date_str, &cfg.region, &cfg.service);
    let signature = hmac_sha256_hex(&signing_key, string_to_sign.as_bytes());

    Some(format!(
        "{} Credential={}/{},SignedHeaders={},Signature={}",
        ALGORITHM, cfg.access_key, credential_scope, signed_hdrs, signature,
    ))
}

fn derive_v4_signing_key(hmac_key: &[u8], date: &str, region: &str, service: &str) -> [u8; 32] {
    let k_date    = hmac_sha256(hmac_key, date.as_bytes());
    let k_region  = hmac_sha256(&k_date, region.as_bytes());
    let k_service = hmac_sha256(&k_region, service.as_bytes());
    hmac_sha256(&k_service, b"aws4_request")
}

// ── SigV4a ────────────────────────────────────────────────────────────────────

fn sign_v4a(
    method: &str,
    uri_path: &str,
    query_str: &str,
    canonical_hdrs: &str,
    signed_hdrs: &str,
    datetime_str: &str,
    date_str: &str,
    payload_hash: &str,
    cfg: &AwsSignerConfig,
) -> Option<String> {
    const ALGORITHM: &str = "AWS4-ECDSA-P256-SHA256";

    let canonical_request = [
        method,
        &uri_encode_path(uri_path),
        &canonical_query_string(query_str),
        canonical_hdrs,
        signed_hdrs,
        payload_hash,
    ]
    .join("\n");

    let credential_scope = format!("{}/{}/aws4_request", date_str, cfg.service);

    let string_to_sign = format!(
        "{}\n{}\n{}\n{}",
        ALGORITHM,
        datetime_str,
        credential_scope,
        sha256_hex(canonical_request.as_bytes()),
    );

    let signing_key = match derive_v4a_signing_key(&cfg.v4a_hmac_key, &cfg.access_key) {
        Ok(k)  => k,
        Err(e) => {
            warn!("aws_sigv4: SigV4a key derivation failed: {}", e);
            return None;
        }
    };

    let digest = Sha256::new_with_prefix(string_to_sign.as_bytes());
    let sig: p256::ecdsa::Signature = signing_key.sign_digest(digest);
    let signature = hex::encode(sig.to_der().as_bytes());

    Some(format!(
        "{} Credential={}/{},SignedHeaders={},Signature={}",
        ALGORITHM, cfg.access_key, credential_scope, signed_hdrs, signature,
    ))
}

// ── Crypto primitives ─────────────────────────────────────────────────────────

fn sha256_hex(data: &[u8]) -> String {
    hex::encode(Sha256::digest(data))
}

fn hmac_sha256(key: &[u8], msg: &[u8]) -> [u8; 32] {
    let mut mac = HmacSha256::new_from_slice(key).expect("HMAC accepts any key length");
    mac.update(msg);
    mac.finalize().into_bytes().into()
}

fn hmac_sha256_hex(key: &[u8], msg: &[u8]) -> String {
    hex::encode(hmac_sha256(key, msg))
}

fn constant_time_less_or_equal(a: &[u8; 32], b: &[u8; 32]) -> bool {
    let mut gt: u8 = 0;
    let mut eq: u8 = 1;

    for i in 0..32 {
        let ai = a[i];
        let bi = b[i];

        let diff = (bi as i32) - (ai as i32);
        let diff_sign = (diff >> 31) as u8;
        gt |= diff_sign & eq;

        let xor = (ai ^ bi) as i32;
        let xor_minus_1 = xor - 1;
        let xor_sign = (xor_minus_1 >> 31) as u8;
        eq &= xor_sign & 0x01;
    }

    (gt as i32) + (gt as i32) + (eq as i32) - 1 <= 0
}

fn derive_v4a_signing_key(
    hmac_key: &[u8],
    access_key: &str,
) -> Result<p256::ecdsa::SigningKey, String> {
    const ALGORITHM: &str = "AWS4-ECDSA-P256-SHA256";

    let n_minus_2: [u8; 32] = [
        0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0xBC, 0xE6, 0xFA, 0xAD, 0xA7, 0x17, 0x9E, 0x84,
        0xF3, 0xB9, 0xCA, 0xC2, 0xFC, 0x63, 0x25, 0x4F,
    ];

    let mut fixed_input: Vec<u8> = Vec::with_capacity(
        4 + ALGORITHM.len() + 1 + access_key.len() + 1 + 4
    );
    fixed_input.extend_from_slice(&[0x00, 0x00, 0x00, 0x01]);
    fixed_input.extend_from_slice(ALGORITHM.as_bytes());
    fixed_input.push(0x00);
    fixed_input.extend_from_slice(access_key.as_bytes());
    
    let counter_index = fixed_input.len();
    fixed_input.push(0x00);
    
    fixed_input.extend_from_slice(&[0x00, 0x00, 0x01, 0x00]);

    for counter in 1_u8..=254 {
        fixed_input[counter_index] = counter;

        let k0 = hmac_sha256(hmac_key, &fixed_input);

        if constant_time_less_or_equal(&k0, &n_minus_2) {
            let mut d = k0;
            let mut carry: u16 = 1;
            for byte in d.iter_mut().rev() {
                let sum = *byte as u16 + carry;
                *byte = sum as u8;
                carry = sum >> 8;
            }
            if let Ok(key) = p256::ecdsa::SigningKey::from_slice(&d) {
                return Ok(key);
            }
        }
    }

    Err(format!(
        "key derivation failed after 254 iterations for access_key={}",
        access_key,
    ))
}

// ── URI utilities ─────────────────────────────────────────────────────────────

fn uri_encode_path(path: &str) -> String {
    path.split('/').map(|seg| uri_encode(&percent_decode(seg))).collect::<Vec<_>>().join("/")
}

fn uri_encode(s: &str) -> String {
    const HEX_CHARS: &[u8] = b"0123456789ABCDEF";
    let mut out = String::with_capacity(s.len());
    for byte in s.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            out.push(byte as char);
        } else {
            out.push('%');
            out.push(HEX_CHARS[(byte >> 4) as usize] as char);
            out.push(HEX_CHARS[(byte & 0x0F) as usize] as char);
        }
    }
    out
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hi = (bytes[i + 1] as char).to_digit(16);
            let lo = (bytes[i + 2] as char).to_digit(16);
            if let (Some(h), Some(l)) = (hi, lo) {
                out.push((h * 16 + l) as u8);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn canonical_query_string(query: &str) -> String {
    if query.is_empty() {
        return String::new();
    }
    let mut params: Vec<(String, String)> = query
        .split('&')
        .filter_map(|pair| {
            let mut it = pair.splitn(2, '=');
            let k = it.next().filter(|s| !s.is_empty())?;
            let v = it.next().unwrap_or("");
            Some((
                uri_encode(&percent_decode(k)),
                uri_encode(&percent_decode(v)),
            ))
        })
        .collect();
    params.sort();
    params.iter().map(|(k, v)| format!("{}={}", k, v)).collect::<Vec<_>>().join("&")
}

// ── Date / time ───────────────────────────────────────────────────────────────

// Converts an Envoy nanosecond timestamp to (YYYYMMDD, YYYYMMDDTHHmmssZ).
// Uses Howard Hinnant's civil calendar algorithm (pure arithmetic, no OS clock).
// Note: 719468 is the number of days between March 1st year 0 and Jan 1st 1970 (Unix Epoch).
fn format_aws_datetime(time_ns: u64) -> (String, String) {
    let total_secs = time_ns / 1_000_000_000;
    let days = total_secs / 86400;
    let rem  = total_secs % 86400;
    let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    let (y, mo, d) = epoch_days_to_ymd(days);
    (
        format!("{:04}{:02}{:02}", y, mo, d),
        format!("{:04}{:02}{:02}T{:02}{:02}{:02}Z", y, mo, d, h, m, s),
    )
}

fn epoch_days_to_ymd(days: u64) -> (u64, u64, u64) {
    let z   = days + 719468;
    let era = z / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y   = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp  = (5 * doy + 2) / 153;
    let d   = doy - (153 * mp + 2) / 5 + 1;
    let m   = if mp < 10 { mp + 3 } else { mp - 9 };
    let y   = if m <= 2 { y + 1 } else { y };
    (y, m, d)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    include!("tests/tests.rs");
}
// [END serviceextensions_plugin_aws_sigv4]
