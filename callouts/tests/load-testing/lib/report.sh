#!/bin/bash
# Report generation functions for load testing framework

# Helper function for floating-point comparison
# Returns 0 (true) if $1 > $2, 1 (false) otherwise
# Uses bc if available, falls back to awk
_float_gt() {
    local a="$1"
    local b="$2"
    if command -v bc >/dev/null 2>&1; then
        (( $(echo "$a > $b" | bc -l) ))
    else
        awk "BEGIN {exit !($a > $b)}"
    fi
}

# Returns 0 (true) if $1 < $2, 1 (false) otherwise
_float_lt() {
    local a="$1"
    local b="$2"
    if command -v bc >/dev/null 2>&1; then
        (( $(echo "$a < $b" | bc -l) ))
    else
        awk "BEGIN {exit !($a < $b)}"
    fi
}

# Generate markdown report
generate_markdown_report() {
    local service_type="$1"
    local test_mode="$2"
    local scenario="$3"
    local file_prefix="$4"
    local results_dir="$5"
    local test_duration="$6"
    local test_vus="$7"
    local warmup_duration="${8:-0}"

    local report_file="$results_dir/${file_prefix}_load_test_report.md"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    cat > "$report_file" << EOF
# Load Test Report

**Generated:** $timestamp
**Service Type:** $service_type
**Test Mode:** $test_mode
**Scenario:** $scenario
**Duration:** $test_duration
**Virtual Users:** $test_vus
EOF

    if [ "$warmup_duration" != "0" ] && [ "$warmup_duration" != "0s" ]; then
        echo "**Warmup:** $warmup_duration" >> "$report_file"
    fi

    echo >> "$report_file"
    echo "## Summary" >> "$report_file"
    echo >> "$report_file"

    # Add ghz summary
    if [ -f "$results_dir/${file_prefix}_ghz_results.json" ]; then
        echo '### ghz Summary' >> "$report_file"
        echo >> "$report_file"
        echo '```json' >> "$report_file"
        jq '{count, total, average, fastest, slowest, rps, statusCodeDistribution}' "$results_dir/${file_prefix}_ghz_results.json" >> "$report_file"
        echo '```' >> "$report_file"
        echo >> "$report_file"
    fi

    # Add load test metrics
    if [ -f "$results_dir/${file_prefix}_load_test_metrics.json" ]; then
        local metrics_data=$(cat "$results_dir/${file_prefix}_load_test_metrics.json")

        cat >> "$report_file" << EOF
### Load Test Metrics

| Metric | Value |
|--------|-------|
| Total Requests | $(echo "$metrics_data" | jq -r '.requests.total') |
| Successful Requests | $(echo "$metrics_data" | jq -r '.requests.ok') |
| Failed Requests | $(echo "$metrics_data" | jq -r '.requests.errors') |
| Success Rate | $(echo "$metrics_data" | jq -r '.requests.success_rate_percent | . * 10000 | round / 10000')% |
| Error Rate | $(echo "$metrics_data" | jq -r '.requests.error_rate_percent | . * 10000 | round / 10000')% |
| Requests/sec | $(echo "$metrics_data" | jq -r '.throughput.rps | round') |

### Response Time Distribution

| Percentile | Latency |
|------------|---------|
| Fastest | $(echo "$metrics_data" | jq -r '.response_times.fastest | . * 100 | round / 100')ms |
| Average | $(echo "$metrics_data" | jq -r '.response_times.average | . * 100 | round / 100')ms |
| 50th (p50) | $(echo "$metrics_data" | jq -r '.response_times.p50 | . * 100 | round / 100')ms |
| 75th (p75) | $(echo "$metrics_data" | jq -r '.response_times.p75 | . * 100 | round / 100')ms |
| 90th (p90) | $(echo "$metrics_data" | jq -r '.response_times.p90 | . * 100 | round / 100')ms |
| 95th (p95) | $(echo "$metrics_data" | jq -r '.response_times.p95 | . * 100 | round / 100')ms |
| 99th (p99) | $(echo "$metrics_data" | jq -r '.response_times.p99 | . * 100 | round / 100')ms |
| Slowest | $(echo "$metrics_data" | jq -r '.response_times.slowest | . * 100 | round / 100')ms |

EOF

        # Add error distribution if there are errors
        local errors=$(echo "$metrics_data" | jq -r '.requests.errors')
        if [ "$errors" -gt 0 ]; then
            echo "### Error Distribution" >> "$report_file"
            echo >> "$report_file"
            echo '```json' >> "$report_file"
            echo "$metrics_data" | jq '.error_distribution' >> "$report_file"
            echo '```' >> "$report_file"
            echo >> "$report_file"
        fi
    fi

    # Add system resource usage
    if [ -f "$results_dir/${file_prefix}_system_metrics.json" ]; then
        local sys_data=$(cat "$results_dir/${file_prefix}_system_metrics.json")

        cat >> "$report_file" << EOF
### System Resource Usage

| Resource | Average | Maximum | Minimum |
|----------|---------|---------|---------|
| CPU Usage | $(echo "$sys_data" | jq -r '.cpu.average | . * 100 | round / 100')% | $(echo "$sys_data" | jq -r '.cpu.maximum | . * 100 | round / 100')% | $(echo "$sys_data" | jq -r '.cpu.minimum | . * 100 | round / 100')% |
| Memory Usage | $(echo "$sys_data" | jq -r '.memory.average | . * 100 | round / 100')% | $(echo "$sys_data" | jq -r '.memory.maximum | . * 100 | round / 100')% | $(echo "$sys_data" | jq -r '.memory.minimum | . * 100 | round / 100')% |

EOF
    fi

    # Add raw data files section
    cat >> "$report_file" << EOF
## Raw Data Files

- **ghz Results:** \`${file_prefix}_ghz_results.json\`
- **Request Data:** \`${file_prefix}_request.json\`
- **Docker Stats:** \`${file_prefix}_docker_stats.json\`
- **System Metrics:** \`${file_prefix}_system_metrics.json\`
- **Load Test Metrics:** \`${file_prefix}_load_test_metrics.json\`
EOF

    # Add export files if they exist
    if [ -f "$results_dir/${file_prefix}_prometheus.txt" ]; then
        echo "- **Prometheus Metrics:** \`${file_prefix}_prometheus.txt\`" >> "$report_file"
    fi
    if [ -f "$results_dir/${file_prefix}_influxdb.txt" ]; then
        echo "- **InfluxDB Metrics:** \`${file_prefix}_influxdb.txt\`" >> "$report_file"
    fi

    cat >> "$report_file" << EOF

---
*Report generated by load testing framework*
EOF

    log_success "Report: $report_file"
}

# Generate comparison report
generate_comparison_report() {
    local comparison_file="$1"
    local output_file="$2"

    if [ ! -f "$comparison_file" ]; then
        log_error "Comparison file not found"
        return 1
    fi

    local data=$(cat "$comparison_file")
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    cat > "$output_file" << EOF
# Load Test Comparison Report

**Generated:** $timestamp

## Comparison Summary

| Metric | Run 1 | Run 2 | Change |
|--------|-------|-------|--------|
| Requests/sec | $(echo "$data" | jq -r '.run1.throughput.rps | round') | $(echo "$data" | jq -r '.run2.throughput.rps | round') | $(echo "$data" | jq -r '.comparison.rps_change_percent | if . == null then "N/A" else ((. * 100 | round) / 100 | tostring) + "%" end') |
| Avg Latency | $(echo "$data" | jq -r '.run1.response_times.average | (. * 100 | round) / 100')ms | $(echo "$data" | jq -r '.run2.response_times.average | (. * 100 | round) / 100')ms | $(echo "$data" | jq -r '.comparison.avg_latency_change_percent | if . == null then "N/A" else ((. * 100 | round) / 100 | tostring) + "%" end') |
| P95 Latency | $(echo "$data" | jq -r '.run1.response_times.p95 | (. * 100 | round) / 100')ms | $(echo "$data" | jq -r '.run2.response_times.p95 | (. * 100 | round) / 100')ms | $(echo "$data" | jq -r '.comparison.p95_latency_change_percent | if . == null then "N/A" else ((. * 100 | round) / 100 | tostring) + "%" end') |
| Error Rate | $(echo "$data" | jq -r '.run1.requests.error_rate_percent | (. * 100 | round) / 100')% | $(echo "$data" | jq -r '.run2.requests.error_rate_percent | (. * 100 | round) / 100')% | $(echo "$data" | jq -r '.comparison.error_rate_change // 0 | (. * 100 | round) / 100')pp |

## Analysis

EOF

    # Add analysis based on comparison (handle null values from zero baseline)
    local rps_change=$(echo "$data" | jq -r '.comparison.rps_change_percent // empty')
    local latency_change=$(echo "$data" | jq -r '.comparison.avg_latency_change_percent // empty')

    if [ -z "$rps_change" ] || [ "$rps_change" = "null" ]; then
        echo "- ℹ️ **Throughput:** Cannot compare (baseline was zero)" >> "$output_file"
    elif _float_gt "$rps_change" 5; then
        echo "- ✅ **Throughput improved** by ${rps_change}%" >> "$output_file"
    elif _float_lt "$rps_change" -5; then
        echo "- ⚠️ **Throughput decreased** by ${rps_change}%" >> "$output_file"
    else
        echo "- ℹ️ **Throughput stable** (change: ${rps_change}%)" >> "$output_file"
    fi

    if [ -z "$latency_change" ] || [ "$latency_change" = "null" ]; then
        echo "- ℹ️ **Latency:** Cannot compare (baseline was zero)" >> "$output_file"
    elif _float_lt "$latency_change" -5; then
        echo "- ✅ **Latency improved** by ${latency_change}%" >> "$output_file"
    elif _float_gt "$latency_change" 5; then
        echo "- ⚠️ **Latency increased** by ${latency_change}%" >> "$output_file"
    else
        echo "- ℹ️ **Latency stable** (change: ${latency_change}%)" >> "$output_file"
    fi

    cat >> "$output_file" << EOF

---
*Comparison report generated by load testing framework*
EOF

    log_success "Comparison report: $output_file"
}

