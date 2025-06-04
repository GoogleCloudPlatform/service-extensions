# Load Testing for Update Header Callout

This directory contains load testing tools for the header update callout service that modifies request and response headers.

## Features Tested
- Request header modification (`header-request: request-new-value`)
- Response header modification (`header-response: response-new-value`)
- Header overwrite behavior (`OVERWRITE_IF_EXISTS_OR_ADD`)
- Clear route cache functionality
- Full request/response cycle performance

## Prerequisites

1. Install [ghz](https://ghz.sh) (v0.118.0+)
2. Install [jq](https://stedolan.github.io/jq/) for results processing
3. Ensure the callout server is running
4. Protobuf definitions available in `protodef/` directory

## Running the Load Test

```bash
./load_test.sh [total_requests] [concurrency]
```

# Default test (1000 requests, 20 concurrent)
```bash
./load_test.sh
```

# 5000 requests with 50 concurrent connections
```bash
./load_test.sh 5000 50
```