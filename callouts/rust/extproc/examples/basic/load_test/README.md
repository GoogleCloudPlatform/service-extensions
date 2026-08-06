# Load Testing for Add Headers Callout

This directory contains load testing tools for the Add Headers callout service.

## Prerequisites
1. Install [ghz](https://ghz.sh) (v0.118.0 or newer)
2. Ensure callout server is running
3. Install [jq](https://stedolan.github.io/jq/) (`sudo apt install jq`)

## Running the Test
```bash
./load_test.sh [total_requests] [concurrent_connections]
# Example:
./load_test.sh 5000 50
```

### Output
Results will be saved in the `results/` directory with timestamped filenames:
- `.json`: Detailed results in JSON format

## Test Configuration

| Parameter          | Default Value | Description |
|--------------------|---------------|-------------|
| HOST               | localhost     | Callout server host |
| PORT               | 8080          | Callout server port |
| TOTAL_REQUESTS     | 1000          | Total number of requests |
| CONCURRENT         | 20            | Concurrent connections |

## Expected Results
For a properly functioning server, expect:
- Success rate: 100%
- Average latency: < 25ms
- Throughput: > 3000 requests/second
- Error distribution: 0%

### Troubleshooting
- Ensure all proto dependencies are available
- Verify network connectivity to server
- Check CPU/Memory usage on server during test

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.