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

use super::*;

// ── Crypto primitives ─────────────────────────────────────────────────────

#[test]
fn sha256_empty_payload() {
    assert_eq!(
        sha256_hex(b""),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
}

// ── SigV4 key derivation ──────────────────────────────────────────────────

#[test]
fn v4_signing_key_matches_aws_test_suite() {
    const SECRET_KEY: &str = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY";
    const DATE_STR: &str = "20150830";
    const REGION: &str = "us-east-1";
    const SERVICE: &str = "iam";

    let hmac_key = format!("AWS4{}", SECRET_KEY).into_bytes();

    assert_eq!(
        hex::encode(derive_v4_signing_key(&hmac_key, DATE_STR, REGION, SERVICE)),
        "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9",
    );
}

// ── Canonical headers ─────────────────────────────────────────────────────

#[test]
fn canonical_headers_maps_authority_to_host_and_sorts() {
    let headers = vec![
        (":method".into(),    "GET".into()),
        (":path".into(),      "/?Action=ListUsers".into()),
        (":authority".into(), "iam.amazonaws.com".into()),
        ("x-amz-date".into(), "20150830T123600Z".into()),
    ];
    let (canonical, signed) = build_canonical_headers(&headers);
    assert_eq!(canonical, "host:iam.amazonaws.com\nx-amz-date:20150830T123600Z\n");
    assert_eq!(signed, "host;x-amz-date");
}

#[test]
fn canonical_headers_excludes_pseudo_headers() {
    let headers = vec![
        (":method".into(), "GET".into()),
        (":scheme".into(), "https".into()),
        ("host".into(),    "example.com".into()),
    ];
    let (canonical, _) = build_canonical_headers(&headers);
    assert!(!canonical.contains(":method"));
    assert!(!canonical.contains(":scheme"));
    assert!(canonical.contains("host:example.com"));
}

#[test]
fn canonical_headers_joins_duplicate_names_with_comma() {
    let headers = vec![
        (":authority".into(),       "s3.amazonaws.com".into()),
        ("x-amz-meta-tag".into(),   "first".into()),
        ("x-amz-meta-tag".into(),   "second".into()),
    ];
    let (canonical, signed) = build_canonical_headers(&headers);
    assert!(canonical.contains("x-amz-meta-tag:first,second\n"));
    assert!(signed.contains("x-amz-meta-tag"));
    assert_eq!(signed.matches("x-amz-meta-tag").count(), 1);
}

#[test]
fn canonical_headers_collapses_internal_whitespace() {
    let headers = vec![
        (":authority".into(),       "s3.amazonaws.com".into()),
        ("x-amz-meta-tag".into(),   "  first   value  ".into()),
    ];
    let (canonical, _) = build_canonical_headers(&headers);
    assert!(
        canonical.contains("x-amz-meta-tag:first value\n"),
        "expected collapsed whitespace, got: {:?}",
        canonical,
    );
}

// ── URI encoding ──────────────────────────────────────────────────────────

#[test]
fn uri_encode_leaves_unreserved_chars_unchanged() {
    assert_eq!(uri_encode("abcABC123-._~"), "abcABC123-._~");
}

#[test]
fn uri_encode_percent_encodes_space_and_reserved() {
    assert_eq!(uri_encode("hello world"), "hello%20world");
    assert_eq!(uri_encode("a=b"),         "a%3Db");
    assert_eq!(uri_encode("/path"),        "%2Fpath");
}

#[test]
fn uri_encode_path_preserves_slash_separators() {
    assert_eq!(uri_encode_path("/foo/bar baz"), "/foo/bar%20baz");
    assert_eq!(uri_encode_path("/"),             "/");
}

#[test]
fn percent_decode_basic() {
    assert_eq!(percent_decode("hello%20world"), "hello world");
    assert_eq!(percent_decode("foo%2Fbar"),     "foo/bar");
    assert_eq!(percent_decode("no-encoding"),   "no-encoding");
    assert_eq!(percent_decode("a%2fb"),         "a/b");
}

#[test]
fn percent_decode_invalid_escape_preserved() {
    assert_eq!(percent_decode("foo%GGbar"), "foo%GGbar");
}

#[test]
fn uri_encode_path_does_not_double_encode() {
    assert_eq!(uri_encode_path("/bucket/my%20key"), "/bucket/my%20key");
    assert_eq!(uri_encode_path("/bucket/my key"),   "/bucket/my%20key");
}

// ── Canonical query string ────────────────────────────────────────────────

#[test]
fn canonical_query_string_sorts_lexicographically() {
    assert_eq!(
        canonical_query_string("Version=2010-05-08&Action=ListUsers"),
        "Action=ListUsers&Version=2010-05-08",
    );
}

#[test]
fn canonical_query_string_does_not_double_encode() {
    assert_eq!(
        canonical_query_string("email=user%40example.com"),
        "email=user%40example.com"
    );
}

#[test]
fn canonical_query_string_empty_input() {
    assert_eq!(canonical_query_string(""), "");
}

// ── request_has_body ──────────────────────────────────────────────────────

#[test]
fn request_has_body_get_is_always_false() {
    let headers = vec![("content-length".into(), "100".into())];
    assert!(!request_has_body("GET",  &headers));
    assert!(!request_has_body("HEAD", &[]));
    assert!(!request_has_body("OPTIONS", &[]));
}

#[test]
fn request_has_body_post_with_content_length() {
    let headers = vec![("content-length".into(), "42".into())];
    assert!(request_has_body("POST", &headers));
}

#[test]
fn request_has_body_post_with_transfer_encoding() {
    let headers = vec![("transfer-encoding".into(), "chunked".into())];
    assert!(request_has_body("PUT", &headers));
}

#[test]
fn request_has_body_post_without_indicators_is_false() {
    let empty = vec![("content-length".into(), "0".into())];
    assert!(!request_has_body("POST", &empty));
    assert!(!request_has_body("POST", &[]));
}

// ── Date / time ───────────────────────────────────────────────────────────

#[test]
fn format_aws_datetime_epoch_zero() {
    let (date, datetime) = format_aws_datetime(0);
    assert_eq!(date,     "19700101");
    assert_eq!(datetime, "19700101T000000Z");
}

#[test]
fn format_aws_datetime_matches_test_suite_date() {
    // 2015-08-30T12:36:00Z
    let (date, datetime) = format_aws_datetime(1_440_938_160_000_000_000_u64);
    assert_eq!(date,     "20150830");
    assert_eq!(datetime, "20150830T123600Z");
}

// ── Full SigV4 signature ─────────────────────────────────────────────────

#[test]
fn sign_v4_canonical_request_hash_matches_aws_test_suite() {
    let canonical_request = [
        "GET",
        "/",
        "Action=ListUsers&Version=2010-05-08",
        "host:iam.amazonaws.com\nx-amz-date:20150830T123600Z\n",
        "host;x-amz-date",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ]
    .join("\n");

    assert_eq!(
        sha256_hex(canonical_request.as_bytes()),
        "5599feeca6d065c7c80025038896f3f7f008849eacf307aa7d0cf8be7116cea6",
    );
}

#[test]
fn sign_v4_produces_correct_authorization_header() {
    let secret = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY";
    let cfg = AwsSignerConfig {
        access_key:     "AKIDEXAMPLE".into(),
        secret_key:     secret.into(),
        region:         "us-east-1".into(),
        service:        "iam".into(),
        signature_type: SignatureType::V4,
        v4_hmac_key:    format!("AWS4{}", secret).into_bytes(),
        v4a_hmac_key:   format!("AWS4A{}", secret).into_bytes(),
    };
    let headers = vec![
        (":method".into(),    "GET".into()),
        (":path".into(),      "/?Action=ListUsers&Version=2010-05-08".into()),
        (":authority".into(), "iam.amazonaws.com".into()),
        ("x-amz-date".into(), "20150830T123600Z".into()),
    ];
    let (canonical_hdrs, signed_hdrs) = build_canonical_headers(&headers);

    let auth = sign_v4(
        "GET", "/", "Action=ListUsers&Version=2010-05-08",
        &canonical_hdrs, &signed_hdrs,
        "20150830T123600Z", "20150830",
        &sha256_hex(b""),
        &cfg,
    )
    .unwrap();

    assert!(
        auth.contains(
            "Signature=b2e4af44cfad96d9ffa3c5653674a927b9b0995c33de22e1f843745ce37c1d5e"
        ),
        "Unexpected Authorization:\n{}",
        auth,
    );
    assert!(auth.starts_with("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/"));
}

#[test]
fn sign_v4_post_with_body_hash() {
    let secret = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY";
    let cfg = AwsSignerConfig {
        access_key:     "AKIDEXAMPLE".into(),
        secret_key:     secret.into(),
        region:         "us-east-1".into(),
        service:        "iam".into(),
        signature_type: SignatureType::V4,
        v4_hmac_key:    format!("AWS4{}", secret).into_bytes(),
        v4a_hmac_key:   format!("AWS4A{}", secret).into_bytes(),
    };
    let body = b"Action=ListUsers&Version=2010-05-08";
    let headers = vec![
        (":method".into(),      "POST".into()),
        (":path".into(),        "/".into()),
        (":authority".into(),   "iam.amazonaws.com".into()),
        ("x-amz-date".into(),   "20150830T123600Z".into()),
        ("content-type".into(), "application/x-www-form-urlencoded".into()),
    ];
    let (canonical_hdrs, signed_hdrs) = build_canonical_headers(&headers);
    let payload_hash = sha256_hex(body);

    let auth = sign_v4(
        "POST", "/", "",
        &canonical_hdrs, &signed_hdrs,
        "20150830T123600Z", "20150830",
        &payload_hash,
        &cfg,
    )
    .unwrap();

    assert!(auth.starts_with("AWS4-HMAC-SHA256 "));
    assert_ne!(
        payload_hash,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
}

// ── SigV4a ────────────────────────────────────────────────────────────────

#[test]
fn v4a_signing_key_derivation_succeeds() {
    let hmac_key = format!("AWS4A{}", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY").into_bytes();
    let result = derive_v4a_signing_key(
        &hmac_key,
        "AKIDEXAMPLE",
    );
    assert!(result.is_ok());
}

#[test]
fn sign_v4a_produces_ecdsa_p256_authorization_header() {
    let secret = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY";
    let cfg = AwsSignerConfig {
        access_key:     "AKIDEXAMPLE".into(),
        secret_key:     secret.into(),
        region:         "*".into(),
        service:        "s3".into(),
        signature_type: SignatureType::V4a,
        v4_hmac_key:    format!("AWS4{}", secret).into_bytes(),
        v4a_hmac_key:   format!("AWS4A{}", secret).into_bytes(),
    };
    let headers = vec![
        (":method".into(),          "GET".into()),
        (":path".into(),            "/my-bucket/my-key".into()),
        (":authority".into(),       "s3.amazonaws.com".into()),
        ("x-amz-date".into(),       "20150830T123600Z".into()),
        ("x-amz-region-set".into(), "*".into()),
    ];
    let (canonical_hdrs, signed_hdrs) = build_canonical_headers(&headers);

    let auth = sign_v4a(
        "GET", "/my-bucket/my-key", "",
        &canonical_hdrs, &signed_hdrs,
        "20150830T123600Z", "20150830",
        &sha256_hex(b""),
        &cfg,
    )
    .unwrap();

    assert!(auth.starts_with("AWS4-ECDSA-P256-SHA256 Credential=AKIDEXAMPLE/"));
    // DER-encoded ECDSA-P256 signature: 70–72 bytes = 140–144 hex chars.
    let sig_hex = auth.split("Signature=").nth(1).unwrap_or("");
    assert!((140..=144).contains(&sig_hex.len()),
        "expected DER signature (140-144 hex chars), got {} chars: {}", sig_hex.len(), sig_hex);
    assert!(!auth.contains("us-east-1"));
}

#[test]
fn sign_v4a_credential_scope_excludes_region() {
    let secret = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY";
    let cfg = AwsSignerConfig {
        access_key:     "AKIDEXAMPLE".into(),
        secret_key:     secret.into(),
        region:         "us-east-1,us-west-2".into(),
        service:        "s3".into(),
        signature_type: SignatureType::V4a,
        v4_hmac_key:    format!("AWS4{}", secret).into_bytes(),
        v4a_hmac_key:   format!("AWS4A{}", secret).into_bytes(),
    };
    let headers = vec![
        (":authority".into(), "s3.amazonaws.com".into()),
        ("x-amz-date".into(), "20150830T123600Z".into()),
        ("x-amz-region-set".into(), "us-east-1,us-west-2".into()),
    ];
    let (canonical_hdrs, signed_hdrs) = build_canonical_headers(&headers);

    let auth = sign_v4a(
        "GET", "/", "",
        &canonical_hdrs, &signed_hdrs,
        "20150830T123600Z", "20150830",
        &sha256_hex(b""),
        &cfg,
    )
    .unwrap();

    assert!(auth.contains("20150830/s3/aws4_request"));
    assert!(!auth.contains("20150830/us-east-1"));
}
