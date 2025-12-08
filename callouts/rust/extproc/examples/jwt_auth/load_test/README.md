# Load Testing for JWT Validation Callout

This directory contains load testing tools for the JWT Validation callout service.

## Prerequisites
1. Install [ghz](https://ghz.sh) (v0.118.0 or newer)
2. Ensure callout server is running
3. Install [jq](https://stedolan.github.io/jq/) (`sudo apt install jq`)

## Running the Test
```bash
./load_test.sh [total_requests] [concurrent_connections]
# Example:
./load_test.sh 4000 30
```

## Test Configuration

| Parameter          | Default Value | Description |
|--------------------|---------------|-------------|
| VALID_TOKEN        | JWT           | Preconfigured valid token |
| INVALID_TOKEN      | JWT           | Token with invalid signature |
| TOTAL_REQUESTS     | 1000          | Total number of requests |

## Expected Results
For a properly functioning server, expect:
- Valid JWT	    : 100% success rate
- Invalid JWT	: 100% denial rate

### Troubleshooting
- Ensure all proto dependencies are available
- Verify network connectivity to server
- Check CPU/Memory usage on server during test

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.