# Load Testing for Add Body Callout

This directory contains load testing tools and configurations for the Add Body callout service.

## Prerequisites

1. Install [ghz](https://ghz.sh), the load testing tool for gRPC services (v0.118.0 or newer)
2. Ensure the callout server is running
3. Install [jq](https://stedolan.github.io/jq/) for detailed summary reports (`sudo apt install jq`)

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

### Output
Results will be saved in the `results/` directory with timestamped filenames:
- `.json`: Detailed results in JSON format
- `.html`: Visual report in HTML format

## Test Configuration

| Parameter          | Default Value | Description |
|--------------------|---------------|-------------|
| HOST               | localhost     | Callout server host |
| PORT               | 8443          | Callout server port |
| TOTAL_REQUESTS     | 1000          | Total number of requests |
| CONCURRENT         | 20            | Concurrent connections |
| REQUEST_DATA       | JSON payload  | Base64-encoded request body |


## Server Setup
   ```bash
   sudo docker run -p 8443:443 -e run_module=extproc.example.e2e_tests.observability_server callout-service-example
   ```

## Troubleshooting
If tests fail with connection errors:

Verify the server is running on the correct port
Check for "connection refused" errors (server not running)
Check for "connection reset by peer" errors (protocol mismatch)
Ensure correct port mapping in Docker with -p 8443:443

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.