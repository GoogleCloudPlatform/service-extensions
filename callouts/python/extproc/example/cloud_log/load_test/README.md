# Load Testing for Cloud Log Callout

This directory contains load testing tools and configurations for the Cloud Log callout service.

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

## Test Configuration

| Parameter          | Default Value | Description |
|--------------------|---------------|-------------|
| HOST               | localhost     | Callout server host |
| PORT               | 8080          | Callout server port |
| TOTAL_REQUESTS     | 1000          | Total number of requests |
| CONCURRENT         | 20            | Concurrent connections |
| REQUEST_DATA       | JSON payload  | Base64-encoded request body |

## Request Types
Success Request: Includes required headers and body.
Fail Request: Missing required headers.

## Expected Results
The success request should yield:

- High success rate (near 100%).
- Average latency and throughput as expected for a functioning server.

For the fail request, expect:
- Low success rate.
- Proper handling of the missing headers.

## Performance Comparison
The script will compare results from the successful and failed requests, providing insights into average latencies, requests per second (RPS), and success rates.

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
  -d '[{"request_headers": {"headers": {"headers": [{"key": "header-check", "raw_value": "c29tZS12YWx1ZQ=="}]},"end_of_stream": true}},{"request_body": {"body": "Ym9keS1jaGVjaw==", "end_of_stream": true}}]' \
  localhost:8080 \
  envoy.service.ext_proc.v3.ExternalProcessor/Process
   ```

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.