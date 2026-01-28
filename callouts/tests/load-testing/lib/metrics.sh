#!/bin/bash
# Metrics analysis functions for load testing framework

# Analyze Docker stats and generate system metrics
analyze_docker_stats() {
    local file_prefix="$1"
    local results_dir="$2"
    local docker_stats_file="$results_dir/${file_prefix}_docker_stats.json"

    if [ ! -f "$docker_stats_file" ] || [ ! -s "$docker_stats_file" ]; then
        log_warning "No Docker stats data found"
        return 1
    fi

    log_info "Analyzing Docker stats..."

    # Finalize JSON array if needed
    if ! jq -e '.' "$docker_stats_file" >/dev/null 2>&1; then
        log_info "Finalizing docker stats: $(basename $docker_stats_file)"
        sed -i 's/,$//' "$docker_stats_file"
        if ! grep -q '^\]$' "$docker_stats_file"; then
            echo "]" >> "$docker_stats_file"
        fi
    fi

    # Calculate CPU and memory statistics
    local cpu_values=$(jq -r '.[].cpu | gsub("%"; "") | tonumber' "$docker_stats_file" 2>/dev/null | grep -v '^$')
    local mem_values=$(jq -r '.[].memory | gsub("%"; "") | tonumber' "$docker_stats_file" 2>/dev/null | grep -v '^$')

    if [ -z "$cpu_values" ] || [ -z "$mem_values" ]; then
        log_warning "No valid CPU/memory data found"
        return 1
    fi

    local avg_cpu=$(echo "$cpu_values" | awk '{sum+=$1} END {print sum/NR}')
    local max_cpu=$(echo "$cpu_values" | sort -n | tail -1)
    local min_cpu=$(echo "$cpu_values" | sort -n | head -1)

    local avg_mem=$(echo "$mem_values" | awk '{sum+=$1} END {print sum/NR}')
    local max_mem=$(echo "$mem_values" | sort -n | tail -1)
    local min_mem=$(echo "$mem_values" | sort -n | head -1)

    jq -n \
        --argjson avg_cpu "$avg_cpu" \
        --argjson max_cpu "$max_cpu" \
        --argjson min_cpu "$min_cpu" \
        --argjson avg_mem "$avg_mem" \
        --argjson max_mem "$max_mem" \
        --argjson min_mem "$min_mem" \
        '{
            cpu: {
                average: $avg_cpu,
                maximum: $max_cpu,
                minimum: $min_cpu
            },
            memory: {
                average: $avg_mem,
                maximum: $max_mem,
                minimum: $min_mem
            }
        }' > "$results_dir/${file_prefix}_system_metrics.json"

    log_success "Docker stats analysis completed"
}

# Analyze ghz results and generate load test metrics
analyze_ghz_results() {
    local file_prefix="$1"
    local results_dir="$2"
    local ghz_file="$results_dir/${file_prefix}_ghz_results.json"

    if [ ! -f "$ghz_file" ] || [ ! -s "$ghz_file" ]; then
        log_warning "No ghz results data found"
        return 1
    fi

    log_info "Analyzing ghz results..."

    # Extract comprehensive metrics from ghz JSON output
    # ghz outputs latency in nanoseconds, convert to milliseconds
    jq '
    def to_ms: . / 1000000;
    def safe_percentile(p): 
        if .latencyDistribution then 
            (.latencyDistribution[] | select(.percentage == p) | .latency) // 0 | to_ms 
        else 0 end;
    {
        response_times: {
            fastest: ((.fastest // 0) | to_ms),
            slowest: ((.slowest // 0) | to_ms),
            average: ((.average // 0) | to_ms),
            p50: safe_percentile(50),
            p75: safe_percentile(75),
            p90: safe_percentile(90),
            p95: safe_percentile(95),
            p99: safe_percentile(99)
        },
        requests: {
            total: (.count // 0),
            ok: (.statusCodeDistribution.OK // 0),
            errors: ((.count // 0) - (.statusCodeDistribution.OK // 0))
        },
        throughput: {
            rps: (.rps // 0),
            total_time_ms: ((.total // 0) | to_ms)
        },
        error_distribution: (.statusCodeDistribution // {}),
        errors_detail: (.errorDistribution // {})
    } | .requests.error_rate_percent = (if .requests.total > 0 then (.requests.errors * 100 / .requests.total) else 0 end)
      | .requests.success_rate_percent = (if .requests.total > 0 then (.requests.ok * 100 / .requests.total) else 0 end)
    ' "$ghz_file" > "$results_dir/${file_prefix}_load_test_metrics.json"

    if [ ! -s "$results_dir/${file_prefix}_load_test_metrics.json" ]; then
        log_warning "No metrics found in ghz results"
        return 1
    fi

    log_success "ghz results analysis completed"
}

# Compare two test runs
compare_runs() {
    local run1_dir="$1"
    local run2_dir="$2"
    local output_file="$3"

    log_info "Comparing test runs..."

    local metrics1=$(find "$run1_dir" -name "*_load_test_metrics.json" | head -1)
    local metrics2=$(find "$run2_dir" -name "*_load_test_metrics.json" | head -1)

    if [ ! -f "$metrics1" ] || [ ! -f "$metrics2" ]; then
        log_error "Could not find metrics files in one or both directories"
        return 1
    fi

    # Calculate comparison metrics with zero-division protection
    # If baseline value is 0, use null to indicate comparison is not meaningful
    jq -s '
    def safe_percent_change(new; old):
        if old == 0 or old == null then
            if new == 0 or new == null then 0
            else null  # Cannot calculate % change from zero baseline
            end
        else ((new - old) / old * 100)
        end;
    {
        run1: .[0],
        run2: .[1],
        comparison: {
            rps_change_percent: safe_percent_change(.[1].throughput.rps; .[0].throughput.rps),
            avg_latency_change_percent: safe_percent_change(.[1].response_times.average; .[0].response_times.average),
            p95_latency_change_percent: safe_percent_change(.[1].response_times.p95; .[0].response_times.p95),
            error_rate_change: ((.[1].requests.error_rate_percent // 0) - (.[0].requests.error_rate_percent // 0))
        }
    }
    ' "$metrics1" "$metrics2" > "$output_file"

    log_success "Comparison complete: $output_file"
}

# Export metrics in Prometheus format
export_prometheus() {
    local file_prefix="$1"
    local results_dir="$2"
    local service_type="$3"
    local test_mode="$4"

    local metrics_file="$results_dir/${file_prefix}_load_test_metrics.json"
    local output_file="$results_dir/${file_prefix}_prometheus.txt"

    if [ ! -f "$metrics_file" ]; then
        log_warning "No metrics file found for Prometheus export"
        return 1
    fi

    log_info "Exporting metrics in Prometheus format..."

    local metrics=$(cat "$metrics_file")
    local labels="service=\"$service_type\",mode=\"$test_mode\""

    cat > "$output_file" << EOF
# HELP load_test_requests_total Total number of requests
# TYPE load_test_requests_total counter
load_test_requests_total{$labels} $(echo "$metrics" | jq -r '.requests.total')

# HELP load_test_requests_success_total Total successful requests
# TYPE load_test_requests_success_total counter
load_test_requests_success_total{$labels} $(echo "$metrics" | jq -r '.requests.ok')

# HELP load_test_requests_error_total Total failed requests
# TYPE load_test_requests_error_total counter
load_test_requests_error_total{$labels} $(echo "$metrics" | jq -r '.requests.errors')

# HELP load_test_error_rate_percent Error rate percentage
# TYPE load_test_error_rate_percent gauge
load_test_error_rate_percent{$labels} $(echo "$metrics" | jq -r '.requests.error_rate_percent')

# HELP load_test_rps Requests per second
# TYPE load_test_rps gauge
load_test_rps{$labels} $(echo "$metrics" | jq -r '.throughput.rps')

# HELP load_test_latency_avg_ms Average latency in milliseconds
# TYPE load_test_latency_avg_ms gauge
load_test_latency_avg_ms{$labels} $(echo "$metrics" | jq -r '.response_times.average')

# HELP load_test_latency_p50_ms 50th percentile latency in milliseconds
# TYPE load_test_latency_p50_ms gauge
load_test_latency_p50_ms{$labels} $(echo "$metrics" | jq -r '.response_times.p50')

# HELP load_test_latency_p90_ms 90th percentile latency in milliseconds
# TYPE load_test_latency_p90_ms gauge
load_test_latency_p90_ms{$labels} $(echo "$metrics" | jq -r '.response_times.p90')

# HELP load_test_latency_p95_ms 95th percentile latency in milliseconds
# TYPE load_test_latency_p95_ms gauge
load_test_latency_p95_ms{$labels} $(echo "$metrics" | jq -r '.response_times.p95')

# HELP load_test_latency_p99_ms 99th percentile latency in milliseconds
# TYPE load_test_latency_p99_ms gauge
load_test_latency_p99_ms{$labels} $(echo "$metrics" | jq -r '.response_times.p99')
EOF

    log_success "Prometheus metrics exported: $output_file"
}

# Export metrics in InfluxDB line protocol format
export_influxdb() {
    local file_prefix="$1"
    local results_dir="$2"
    local service_type="$3"
    local test_mode="$4"

    local metrics_file="$results_dir/${file_prefix}_load_test_metrics.json"
    local output_file="$results_dir/${file_prefix}_influxdb.txt"

    if [ ! -f "$metrics_file" ]; then
        log_warning "No metrics file found for InfluxDB export"
        return 1
    fi

    log_info "Exporting metrics in InfluxDB line protocol..."

    local metrics=$(cat "$metrics_file")
    local timestamp=$(date +%s%N)

    cat > "$output_file" << EOF
load_test,service=$service_type,mode=$test_mode requests_total=$(echo "$metrics" | jq -r '.requests.total')i,requests_ok=$(echo "$metrics" | jq -r '.requests.ok')i,requests_errors=$(echo "$metrics" | jq -r '.requests.errors')i,error_rate=$(echo "$metrics" | jq -r '.requests.error_rate_percent'),rps=$(echo "$metrics" | jq -r '.throughput.rps'),latency_avg=$(echo "$metrics" | jq -r '.response_times.average'),latency_p50=$(echo "$metrics" | jq -r '.response_times.p50'),latency_p90=$(echo "$metrics" | jq -r '.response_times.p90'),latency_p95=$(echo "$metrics" | jq -r '.response_times.p95'),latency_p99=$(echo "$metrics" | jq -r '.response_times.p99') $timestamp
EOF

    log_success "InfluxDB metrics exported: $output_file"
}

