# Load Testing Framework

A comprehensive Docker-based load testing framework for gRPC services using [ghz](https://ghz.sh/), with automated metrics collection, resource monitoring, Prometheus/InfluxDB export, and detailed reporting.


## Prerequisites

- Docker and Docker Compose
- Docker socket access (for container management)
- At least 4GB RAM available
- Linux, macOS, or Windows with WSL2

> **⚠️ Security Note:** This framework mounts the Docker socket (`/var/run/docker.sock`) to manage test containers dynamically. This grants the load-tester container root-level access to the host's Docker daemon. Only run this framework in trusted environments (development/CI) and never in production. Consider using Docker-in-Docker or rootless Docker for enhanced security.

## Quick Start

### 1. Start the Load Testing Environment

```bash
docker compose up -d
docker compose exec load-tester bash
```

### 2. Run Your First Test

```bash
# Quick smoke test (10s, 10 VUs)
./run-test.sh -s python_basic -m quick

# Standard load test with warmup (30s, 50 VUs, 5s warmup)
./run-test.sh -s python_basic -m standard

# Full comprehensive test (120s, 200 VUs, 15s warmup)
./run-test.sh -s python_basic -m full
```

### 3. View Results

```bash
# Results are automatically saved with timestamps
ls -la results/

# View the latest report
cat results/latest/*_load_test_report.md
```

## Usage

### Command Syntax

```bash
./run-test.sh -s <service> -m <mode> [OPTIONS]
```

### Required Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `-s, --service <type>` | Service type to test | `python_basic`, `java_basic`, `go_basic` |
| `-m, --mode <mode>` | Test mode | `quick`, `standard`, `stress`, `full`, `soak` |

### Optional Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `-n, --scenario <name>` | Scenario name | `default` |
| `-d, --duration <time>` | Override test duration (supports s/m/h) | From test mode |
| `-v, --vus <number>` | Override virtual users | From test mode |
| `-w, --warmup <time>` | Override warmup duration (supports s/m/h) | From test mode |
| `-e, --export <formats>` | Export formats (comma-separated) | `json` |
| `-c, --collect-metrics` | Collect Docker metrics | Enabled |
| `-k, --keep-service` | Keep service running after test | Disabled |
| `--compare <dir1> <dir2>` | Compare two test runs | - |
| `-l, --list-services` | List available services | - |
| `-L, --list-modes` | List available test modes | - |
| `-S, --show-config` | Show full configuration | - |
| `-h, --help` | Show help message | - |

### Duration Formats

The `-d` (duration) and `-w` (warmup) arguments accept flexible time formats:

| Format | Examples | Description |
|--------|----------|-------------|
| Seconds | `30s`, `60s`, `120s`, `30` | Duration in seconds |
| Minutes | `5m`, `10m`, `30m` | Duration in minutes |
| Hours | `1h`, `2h` | Duration in hours |

All durations are internally converted to seconds for consistency.

### Examples

```bash
# List available services
./run-test.sh -l

# List available test modes (with warmup info)
./run-test.sh -L

# Run quick test on python_basic service
./run-test.sh -s python_basic -m quick

# Run with Prometheus and InfluxDB export for Grafana
./run-test.sh -s python_basic -m standard -e json,prometheus,influxdb

# Run test with 30 second warmup
./run-test.sh -s python_basic -m quick -w 30s

# Run 5 minute test with 1 minute warmup
./run-test.sh -s python_basic -m quick -d 5m -w 1m

# Run 1 hour soak test
./run-test.sh -s python_basic -m soak -d 1h

# Compare two test runs
./run-test.sh --compare results/run1 results/run2

# Keep service running after test (for debugging)
./run-test.sh -s python_basic -m quick -k
```

## Configuration

### Test Modes

Defined in `config/test-config.json`:

| Mode | Duration | VUs | Warmup | Description |
|------|----------|-----|--------|-------------|
| `quick` | 10s | 10 | 0s | Quick smoke test |
| `standard` | 30s | 50 | 5s | Standard load test with warmup |
| `stress` | 60s | 100 | 10s | Stress test with warmup |
| `full` | 120s | 200 | 15s | Full comprehensive test with warmup |
| `soak` | 300s | 50 | 30s | Long-running soak test |

### Export Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| `json` | JSON metrics (default) | Raw data analysis |
| `prometheus` | Prometheus exposition format | Grafana dashboards |
| `influxdb` | InfluxDB line protocol | Time-series databases |

Example Prometheus output:
```
# HELP load_test_rps Requests per second
# TYPE load_test_rps gauge
load_test_rps{service="java_basic",mode="quick"} 15186

# HELP load_test_latency_p99_ms 99th percentile latency in milliseconds
# TYPE load_test_latency_p99_ms gauge
load_test_latency_p99_ms{service="java_basic",mode="quick"} 1.43
```

Example InfluxDB output:
```
load_test,service=java_basic,mode=quick requests_total=151861i,rps=15186.04,latency_p99=1.43 1764146051
```


### Service Image Types

The load testing framework supports two types of service images:

#### 1. **Remote Images** (Pre-built, ready to use)

These images are hosted on a container registry and can be pulled automatically. No build step required.

**Example from config:**
```json
{
  "python_basic": {
    "image": "us-docker.pkg.dev/service-extensions-samples/callouts/python-example-basic:main",
    "description": "Basic python example of service extensions"
  }
}
```

**Available remote images examples:**
- `python_basic` - Basic Python service extension example
- `python_jwt_auth` - Python JWT authentication example

#### 2. **Local Images** (Require building first)

These images must be built locally before running tests.

**Example from config:**
```json
{
  "go_basic": {
    "image": "go-callout-example:local",
    "description": "Basic Go example"
  },
  "java_basic": {
    "image": "java-callout-example:local",
    "description": "Basic Java example"
  }
}
```

### Adding a New Service

> **⚠️ Note**: Make sure your custom service image is built and available (either pulled from a registry or built locally) before adding it to the configuration.

Edit `config/test-config.json`:

```json
{
  "service_types": {
    "my_service": {
      "image": "my-service:latest",
      "description": "My custom service",
      "port": 8080,
      "container_port": 8080,
      "health_check_port": 80, 
      "health_check_container_port": 80,
      "command": [],
      "env": {
        "MY_VAR": "value"
      },
      "resources": {
        "cpu_limit": "2.0",
        "memory_limit": "1g",
        "cpu_reservation": "1.0",
        "memory_reservation": "512m"
      },
      "request_data": {
        "type": "request_headers",
        "headers": {
          "headers": [
            {"key": "some-header", "value": "some-value"}
          ]
        },
        "end_of_stream": true
      }
    }
  }
}
```

#### Request Data Types

The `request_data.type` field determines what data is sent in the gRPC ProcessingRequest message. The external processor protocol supports testing both request and response processing phases.

| Type | Description |
|------|-------------|
| `request_headers` | Request headers only (default) |
| `request_body` | Request body only |
| `request_combined` | Request headers followed by body |
| `response_headers` | Response headers only |
| `response_body` | Response body only |
| `response_combined` | Response headers followed by body |

##### Example: Request Headers (Default)
```json
{
  "request_data": {
    "type": "request_headers",
    "headers": {
      "headers": [
        {"key": ":path", "value": "/test"},
        {"key": "x-api-key", "raw_value": "bXktYXBpLWtleQ=="}
      ]
    },
    "end_of_stream": true
  }
}
```

##### Example: Request Combined (Headers + Body)
```json
{
  "request_data": {
    "type": "request_combined",
    "headers": {
      "headers": [
        {"key": "content-type", "value": "application/json"}
      ]
    },
    "body": {
      "body": "eyJrZXkiOiJ2YWx1ZSJ9"
    },
    "end_of_stream": true
  }
}
```

##### Example: Response Headers
```json
{
  "request_data": {
    "type": "response_headers",
    "headers": {
      "headers": [
        {"key": ":status", "value": "200"},
        {"key": "content-type", "value": "application/json"}
      ]
    },
    "end_of_stream": true
  }
}
```

##### Example: Response Body
```json
{
  "request_data": {
    "type": "response_body",
    "body": {
      "body": "SGVsbG8gV29ybGQ="
    },
    "end_of_stream": true
  }
}
```

> **Tip**: Use `value` for string header values or `raw_value` for Base64 encoded binary data. Body data should be Base64 encoded.

## Understanding Results

### Result Directory Structure

Each test run creates a timestamped directory:

```
results/java_basic_quick_default_20251126_083353/
├── *_ghz_results.json          # Raw ghz metrics
├── *_load_test_metrics.json    # Analyzed load test metrics
├── *_docker_stats.json         # Container resource stats
├── *_system_metrics.json       # CPU/memory analysis
├── *_request.json              # Request data used
├── *_prometheus.txt            # Prometheus metrics (if exported)
├── *_influxdb.txt              # InfluxDB metrics (if exported)
└── *_load_test_report.md       # Human-readable report
```

### Report Contents

The markdown report includes:

1. **Test Configuration**: Service, mode, duration, VUs, warmup
2. **ghz Summary**: Raw metrics and status distribution
3. **Load Test Metrics**:
   - Total requests, successes, and errors
   - Success/error rate percentages
   - Requests per second (RPS)
4. **Response Time Distribution**:
   - Fastest, Average, Slowest
   - Percentiles: P50, P75, P90, P95, P99
5. **Error Distribution**: Breakdown by error type
6. **System Resource Usage**: CPU and memory (avg, max, min)

### Example Report

```markdown
# Load Test Report

**Generated:** 2025-11-26 08:34:11
**Service Type:** java_basic
**Test Mode:** quick
**Duration:** 10s
**Virtual Users:** 10

### Load Test Metrics

| Metric | Value |
|--------|-------|
| Total Requests | 151,861 |
| Successful Requests | 151,851 |
| Failed Requests | 10 |
| Success Rate | 99.99% |
| Error Rate | 0.01% |
| Requests/sec | 15,186 |

### Response Time Distribution

| Percentile | Latency |
|------------|---------|
| Fastest | 0.07ms |
| Average | 0.55ms |
| 50th (p50) | 0.45ms |
| 75th (p75) | 0.54ms |
| 90th (p90) | 0.67ms |
| 95th (p95) | 0.80ms |
| 99th (p99) | 1.43ms |
| Slowest | 91.06ms |
```

### Comparison Reports

Compare two test runs to analyze performance changes:

```bash
./run-test.sh --compare results/run1 results/run2
```

Output:
```markdown
# Load Test Comparison Report

| Metric | Run 1 | Run 2 | Change |
|--------|-------|-------|--------|
| Requests/sec | 15,186 | 17,153 | +12.95% |
| Avg Latency | 0.55ms | 0.47ms | -13.79% |
| P95 Latency | 0.80ms | 0.71ms | -10.94% |
| Error Rate | 0.01% | 0.00% | -0.01pp |

## Analysis
- **Throughput improved** by 12.95%
- **Latency improved** by 13.79%
```

## Analyzing Results

### Extract Specific Metrics

```bash
# Get response time percentiles
jq '.response_times' results/latest/*_load_test_metrics.json

# Get throughput
jq '.throughput.rps' results/latest/*_load_test_metrics.json

# Get error rate
jq '.requests.error_rate_percent' results/latest/*_load_test_metrics.json

# Get CPU usage
jq '.cpu' results/latest/*_system_metrics.json
```

### Grafana Integration

##### 1. Export metrics in Prometheus or InfluxDB format:
   ```bash
   ./run-test.sh -s python_basic -m standard -e prometheus,influxdb
   ```

##### 2. Push to your metrics backend:
   ```bash
   # Prometheus (via pushgateway)
   cat results/latest/*_prometheus.txt | curl --data-binary @- http://pushgateway:9091/metrics/job/load_test

   # InfluxDB
   cat results/latest/*_influxdb.txt | curl -XPOST 'http://influxdb:8086/write?db=metrics' --data-binary @-
   ```
