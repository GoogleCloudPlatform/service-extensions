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
| [add_body](samples/add_body/) | Appends `"-added-request-body"` to the request body and replaces the response body with `"new-body"` |

### Header Manipulation

| Sample | Description |
|--------|-------------|
| [add_header](samples/add_header/) | Adds `header-request: request` to requests (clears route cache) and `header-response: response` to responses (removes `foo`) |
| [update_header](samples/update_header/) | Overwrites or adds `header-request` and `header-response` using the `OVERWRITE_IF_EXISTS_OR_ADD` append action |
| [normalize_header](samples/normalize_header/) | Detects device type from `:authority` and injects `client-device-type: mobile/tablet/desktop` |

### Routing & Traffic Management

| Sample | Description |
|--------|-------------|
| [dynamic_forwarding](samples/dynamic_forwarding/) | Routes requests to a backend IP from the `ip-to-return` header; validates against a known address list with fallback to `10.1.10.4` |
| [redirect](samples/redirect/) | Returns an unconditional `301 Moved Permanently` to `http://service-extensions.com/redirect` |

### Authentication & Authorization

| Sample | Description |
|--------|-------------|
| [jwt_auth](samples/jwt_auth/) | Validates RS256 JWT Bearer tokens against an RSA public key; forwards decoded claims as `decoded-<claim>` headers |
| [cloud_log](samples/cloud_log/) | Enforces `header-check` and `body-check` sentinel values; logs authorization decisions to Google Cloud Logging |

### Cookie Management

| Sample | Description |
|--------|-------------|
| [set_cookie](samples/set_cookie/) | Conditionally injects `Set-Cookie` into responses when the `cookie-check` header is present |

### Reference Implementations

| Sample | Description |
|--------|-------------|
| [basic_callout_server](samples/basic_callout_server/) | Full four-phase reference with deny/mock/standard conditional logic across all HTTP processing phases |
| [basic_callout_server_v2](samples/basic_callout_server_v2/) | Extended four-phase reference: rewrites `:authority` and `:path`, injects headers, replaces request body, clears response body; supports CLI arguments |

## Build

Install dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start a specific sample server:
```bash
# As a module
python -m extproc.example.<sample_name>

# Directly
python <sample_name>.py

# With CLI arguments (samples that support them)
python <sample_name>.py --address 0.0.0.0 --port 8443
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