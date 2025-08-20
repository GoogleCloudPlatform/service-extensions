# Load Testing for Header Normalization Callout

This directory contains load testing tools for the header normalization callout service that adds a `client-device-type` header based on the host value.

## Features Tested
- Header normalization based on host value
- Device type detection (mobile, tablet, desktop)
- Header mutation performance
- Clear route cache operation

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