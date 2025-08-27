# Load Testing for Set Cookie Callout

This directory contains load testing tools for the set cookie callout service that conditionally adds a Set-Cookie header to responses.

## Features Tested
- Conditional cookie setting based on header presence
- Response header processing performance
- Header mutation efficiency
- Server behavior under different scenarios

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