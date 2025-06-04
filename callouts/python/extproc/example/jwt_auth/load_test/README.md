# Load Testing for JWT Authentication Callout

This directory contains load testing tools for the JWT authentication callout service that validates tokens and adds decoded claims as headers.

## Features Tested
- JWT token validation (RS256 algorithm)
- Proper denial of invalid tokens
- Header mutation with decoded claims
- Performance under valid and invalid token scenarios
- Error handling and permission denial

## Prerequisites

1. Install [ghz](https://ghz.sh) (v0.118.0+)
2. Install [jq](https://stedolan.github.io/jq/) for results processing
3. Ensure the callout server is running
4. SSL credentials available in `ssl_creds/` directory
5. Protobuf definitions available in `protodef/` directory

## Running the Load Test

Execute the load test script with default parameters:
```bash
./load_test.sh
```

### Custom Parameters
```bash
# Syntax: ./load_test.sh [total_requests] [concurrent_connections]
./load_test.sh 5000 50  # 5000 requests with 50 concurrent connections
```