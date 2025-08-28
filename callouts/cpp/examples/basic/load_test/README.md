# Load Testing for Basic Callout

Comprehensive load testing for the basic callout service handling multiple processing phases.

## Prerequisites

1. Install [ghz](https://ghz.sh), the load testing tool for gRPC services (v0.118.0 or newer)
2. Ensure the callout server is running
3. Install [jq](https://stedolan.github.io/jq/) for detailed summary reports (`sudo apt install jq`)

### Custom Parameters
```bash
# Syntax: ./load_test.sh [total_requests] [concurrent_connections]
./load_test.sh 5000 50  # 5000 requests with 50 concurrent connections
```

# Syntax: ./load_test.sh [total_requests] [concurrent_connections]
./load_test.sh 5000 50  # 5000 requests with 50 concurrent connections

### Output
Results will be saved in the results/ directory with timestamped filenames:
`.json`: Detailed results in JSON format

## Test Configuration

| Parameter          | Default Value | Description |
|--------------------|---------------|-------------|
| HOST               | localhost     | Callout server host |
| PORT               | 8080          | Callout server port |
| TOTAL_REQUESTS     | 1000          | Total number of requests |
| CONCURRENT         | 20            | Concurrent connections |
| REQUEST_DATA       | JSON payload  | Base64-encoded request body |

## Troubleshooting
If tests fail:
1. Verify the callout server is running: `docker ps`
2. Check server logs: `docker logs <container_id>`
3. Test manually using grpcurl:
   ```bash
   grpcurl -plaintext -d '{
      "request_headers": {
         "headers": {
            "headers": [{"key":"Authorization","raw_value":"Bearer eyJhbGciOiJSUzI1NiIs..."}]
         }
      }
   }' localhost:8080 envoy.service.ext_proc.v3.ExternalProcessor/Process
   ```

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.