# Load Testing for Set Header Based on Body

Tests full body buffering and header injection.

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
| TOTAL_REQUESTS     | 1000          | Total number of requests |
| CONCURRENT         | 20            | Concurrent connections |

## Troubleshooting
If tests fail:
1. Verify the callout server is running: `docker ps`
2. Check server logs: `docker logs <container_id>`
3. Test manually using grpcurl:
   ```bash
   grpcurl -proto protodef/envoy/service/ext_proc/v3/external_processor.proto \
   -d '{"request_headers": {"headers": {"headers": [{"key": "example-header", "raw_value": "ZXhhbXBsZS12YWx1ZQ=="}]}}' \
   localhost:8181 envoy.service.ext_proc.v3.ExternalProcessor/Process
   ```

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.