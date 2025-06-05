# Load Testing for Dynamic Forwarding Callout

This directory contains load testing tools and configurations for the Dynamic Forwarding callout service.

## Prerequisites

1. Install [ghz](https://ghz.sh), the load testing tool for gRPC services (v0.118.0 or newer).
2. Ensure the callout server is running.
3. Install [jq](https://stedolan.github.io/jq/) for detailed summary reports (`sudo apt install jq`).

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

## Test Configuration

| Parameter          | Default Value | Description |
|--------------------|---------------|-------------|
| HOST               | localhost     | Callout server host |
| PORT               | 8080          | Callout server port |
| TOTAL_REQUESTS     | 1000          | Total number of requests |
| CONCURRENT         | 20            | Concurrent connections |
| REQUEST_DATA       | JSON payload  | Base64-encoded request body |

## Request Types

- Valid IP Selection: Tests the selection of a specific valid IP.
- Default IP Selection: Tests the selection behavior when a specific IP is not provided.

## Expected Results
For valid IP requests, you should expect:

- High success rate (near 100%).
- Average latency and throughput as needed for the application.

For default requests, ensure that:

- The service handles requests correctly and provides default behavior as expected.

## Sample Report
![Sample Load Test Report](results/sample_report.png)

## Troubleshooting
If tests fail:
1. Verify the callout server is running: `docker ps`
2. Check server logs: `docker logs <container_id>`
3. Test manually using grpcurl:
   ```bash
   grpcurl -proto protodef/envoy/service/ext_proc/v3/external_processor.proto \
  -import-path protodef \
  -plaintext \
  -d '[{"request_headers": {"headers": {"headers": [{"key": "ip-to-return", "raw_value": "MTAuMS4xMC4y"}]},"end_of_stream": true}}]' \
  localhost:8080 \
  envoy.service.ext_proc.v3.ExternalProcessor/Process
   ```

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.