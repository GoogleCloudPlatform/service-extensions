# Python Callout Samples

This directory contains a collection of example ext_proc callout services written in Python, demonstrating various use cases, patterns, and best practices for building Envoy External Processing services. Each sample extends `CalloutServer` and overrides one or more processing phase callbacks.

## Getting Started

Each sample directory contains:
- **Source code** (`*.py`)
- **README.md** with detailed documentation

## Quick Reference

### Body Manipulation

| Sample | Description |
|--------|-------------|
| [add_body](add_body/) | Appends `"-added-request-body"` to the request body and replaces the response body with `"new-body"` |
| [add_custom_response](add_custom_response/) | Replaces the response with a custom status, headers, and body |

### Header Manipulation

| Sample | Description |
|--------|-------------|
| [add_header](add_header/) | Adds `header-request: request` to requests (clears route cache) and `header-response: response` to responses (removes `foo`) |
| [update_header](update_header/) | Overwrites or adds `header-request` and `header-response` using the `OVERWRITE_IF_EXISTS_OR_ADD` append action |
| [normalize_header](normalize_header/) | Detects device type from `:authority` and injects `client-device-type: mobile/tablet/desktop` |

### Routing & Traffic Management

| Sample | Description |
|--------|-------------|
| [dynamic_forwarding](dynamic_forwarding/) | Routes requests to a backend IP from the `ip-to-return` header; validates against a known address list with fallback to `10.1.10.4` |
| [redirect](redirect/) | Returns an unconditional `301 Moved Permanently` to `http://service-extensions.com/redirect` |

### Authentication & Authorization

| Sample | Description |
|--------|-------------|
| [jwt_auth](jwt_auth/) | Validates RS256 JWT Bearer tokens against an RSA public key; forwards decoded claims as `decoded-<claim>` headers |
| [cloud_log](cloud_log/) | Enforces `header-check` and `body-check` sentinel values; logs authorization decisions to Google Cloud Logging |

> Looking for `ext_authz`-based authorization instead of `ext_proc`? See [`../../extauthz/`](../../extauthz/).

### Cookie Management

| Sample | Description |
|--------|-------------|
| [set_cookie](set_cookie/) | Conditionally injects `Set-Cookie` into responses when the `cookie-check` header is present |

### AI / LLM Gateway

| Sample | Description |
|--------|-------------|
| [litellm_gateway](litellm_gateway/) | Full LLM gateway callout, including a Terraform deployment config under `deploy/` |

### Reference Implementations

| Sample | Description |
|--------|-------------|
| [basic](basic/) | Full four-phase reference covering all core callback types — a starting point for a new callout server |

## Build

Install dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start a specific sample server:
```bash
# As a module
python -m extproc.example.<sample_name>.service_callout_example

# With CLI arguments (samples that support them)
python -m extproc.example.<sample_name>.service_callout_example --address 0.0.0.0 --port 8443
```

## Test

Run all tests:
```bash
python -m pytest tests/
```

Run tests for a specific sample:
```bash
# Run sample tests
python -m pytest tests/<sample_name>_test.py

# With verbose output
python -m pytest -v tests/<sample_name>_test.py
```

## Additional Resources

- [Envoy ext_proc documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/ext_proc_filter)
- [service-extensions repository](https://github.com/GoogleCloudPlatform/service-extensions)
- [PyJWT](https://pyjwt.readthedocs.io/)
- [google-cloud-logging](https://cloud.google.com/logging/docs/reference/libraries#client-libraries-install-python)
