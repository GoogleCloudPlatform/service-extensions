# Load Testing for Receive Body Callout

Tests conditional body processing based on headers.

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
| PORT               | 8181          | Callout server port |
| TOTAL_REQUESTS     | 1000          | Total number of requests |
| CONCURRENT         | 20            | Concurrent connections |

## Expected Results
For a properly functioning server, expect:
- Success rate: 100%
- Average latency: < 15ms
- Throughput: > 3500 requests/second

## Troubleshooting
If tests fail:
1. Verify the callout server is running: `docker ps`
2. Check server logs: `docker logs <container_id>`
3. Test manually using grpcurl:
   ```bash
      grpcurl -proto protodef/envoy/service/ext_proc/v3/external_processor.proto \
   -d @ localhost:8181 envoy.service.ext_proc.v3.ExternalProcessor/Process <<EOF
   {
   "request_headers": {
      "headers": {
         "headers": [
         {"key": "x-process-request-body", "value": "true"}
         ]
      }
   }
   }
   EOF
   ```

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.