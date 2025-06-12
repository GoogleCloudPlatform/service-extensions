# Load Testing for Redirect Callout

This directory contains load testing tools for the redirect callout service that returns a 301 redirect response.

## Features Tested
- Immediate response handling (301 redirect)
- Header processing performance
- gRPC server stability under load
- Error rate monitoring

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