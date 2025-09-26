# Load Testing for WAF Callout

Tests streaming WAF functionality with safe content.

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

## Expected Results
For a properly functioning server, expect:
- Success rate: 100%
- Average latency: < 25ms
- Throughput: > 2500 requests/second

## Malicious Test Pattern
To test blocking behavior manually, use:

```{
  "request_body": {
    "body": "U1FMX0lOSkVDVElPTg==",  # Base64 for "SQL_INJECTION"
    "end_of_stream": true
  }
}```

## Maintenance
Update the `REQUEST_DATA` variable in `load_test.sh` if the callout interface changes.