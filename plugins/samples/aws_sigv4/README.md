# AWS SigV4/V4a Request Signing Plugin

This plugin implements request authentication by dynamically generating AWS Signature Version 4 (SigV4) or Version 4a (SigV4a) headers. It intercepts outgoing requests, calculates the required cryptographic hashes based on the request's path, headers, and payload, and mutates the request to include the proper `Authorization` and `x-amz-*` headers. Use this plugin when you need to route proxy traffic securely to AWS APIs (like Amazon S3 or EC2) without requiring the upstream client to handle complex AWS cryptography. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. **Timestamp generation**: The plugin reads the current time and formats it into AWS-compliant chronological date strings (e.g., `YYYYMMDD` and `YYYYMMDDTHHmmssZ`) without relying on OS system clocks.

3. **Payload evaluation**: The plugin checks if the request method implies a body (by inspecting `content-length` or `transfer-encoding`). 
   - If the target service is S3, it leverages the `"UNSIGNED-PAYLOAD"` feature.
   - If targeting non-S3 services, it safely falls back to signing an empty body hash to prevent proxy crashes, issuing a warning in the logs.

4. **Canonicalization**: The plugin extracts the `:method`, `:path`, and query strings, then standardizes and sorts the HTTP headers (collapsing internal whitespace) to build the exact canonical request required by AWS.

5. **Cryptographic signing**: Depending on the configuration, it calculates the signature using the derived signing key:
   - **SigV4**: Uses standard HMAC-SHA256.
   - **SigV4a**: Uses Elliptic Curve cryptography (ECDSA-P256) through a strict derivation loop.

6. **Header mutation**: The plugin injects the computed `Authorization`, `x-amz-date`, and `x-amz-content-sha256` headers . If using SigV4a, it also automatically injects the required `x-amz-region-set` header.

7. **Success**: The plugin returns `Action::Continue`, forwarding the fully authenticated request to the upstream AWS server.

## Implementation Notes

- **Zero Network Overhead**: All mathematical calculations and canonicalizations are executed directly within the WebAssembly sandbox memory, requiring no external callouts.
- **Cryptographic precision**: The SigV4a implementation handles asymmetric curve derivation natively, verifying the key against the `n-2` curve order boundary.

## Configuration

The plugin expects a JSON configuration string during the root context initialization . 

**Configurable fields**:
- **`access_key`** (string): Your AWS Access Key ID.
- **`secret_key`** (string): Your AWS Secret Access Key.
- **`region`** (string): The AWS region (e.g., `"us-east-1"`) or `"*"` for global services.
- **`service`** (string): The AWS service identifier (e.g., `"s3"`, `"ec2"`, `"iam"`).
- **`signature_type`** (string, optional): Set to `"v4"` (default) or `"v4a"`.

**Example Configuration**:
```json
{
  "access_key": "AKIAIOSFODNN7EXAMPLE",
  "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
  "region": "us-east-1",
  "service": "ec2",
  "signature_type": "v4"
}
```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/aws_sigv4:plugin_rust.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/aws_sigv4/tests.textpb \
    --plugin /mnt/bazel-bin/samples/aws_sigv4/plugin_rust.wasm

# Using Bazel for internal Rust tests
bazelisk test --test_output=all //samples/aws_sigv4:plugin_unit_tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **Regional_SigV4_GET** | Intercepts the request and injects valid HMAC-SHA256 headers for standard AWS regional routing. |
| **Global_SigV4a_MRAP** | Switches the cryptographic engine to ECDSA-P256, drops the region from the scope, and correctly injects the `x-amz-region-set` header for global S3 routing. |
| **POST_Body_S3_Handling** | Bypasses memory-heavy payload buffering by successfully applying the `UNSIGNED-PAYLOAD` tag for S3 endpoints. |
| **POST_Body_Non_S3_Fallback** | Detects an incoming body for a strict API (like IAM), logs a warning, and safely signs an empty payload hash `(e3b0c442...)` to prevent proxy exhaustion. |
| **Missing_Credentials** | Logs a warning and allows the request to proceed without the Authorization header if keys are missing from the configuration. |

## Available Languages

- [x] [Rust](plugin.rs)