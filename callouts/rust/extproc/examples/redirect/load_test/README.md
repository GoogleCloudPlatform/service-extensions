# Load Testing for Redirect Callout

This directory contains load testing tools for the Redirect callout service.

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
| User-Agent	     | Mobile Safari | Triggers redirect response |
| Expected Action	 | 301 Redirect	 | To service-extensions.com  |

## Expected Results
For a properly functioning server, expect:
- 100% success rate
- Latency < 20ms average
- Throughput > 3500 req/sec

### Troubleshooting
- Ensure all proto dependencies are available
- Verify network connectivity to server
- Check CPU/Memory usage on server during test

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.