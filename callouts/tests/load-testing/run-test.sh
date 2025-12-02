#!/bin/bash
# Load Testing Framework for Service Extensions
# Supports multiple service types, test modes, and export formats

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load configuration
CONFIG_FILE="${CONFIG_FILE:-$SCRIPT_DIR/config/test-config.json}"
RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"
NETWORK_NAME="${NETWORK_NAME:-load-testing_load-test-network}"

# Source library files
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/docker.sh"
source "$SCRIPT_DIR/lib/metrics.sh"
source "$SCRIPT_DIR/lib/report.sh"

# Default test settings
DEFAULT_SERVICE_TYPE=""
DEFAULT_TEST_MODE=""
DEFAULT_SCENARIO="default"
DEFAULT_COLLECT_METRICS=true
DEFAULT_WAIT_TIMEOUT=60
DEFAULT_EXPORT_FORMATS="json"

# Global variables
TEST_DURATION=""
TEST_VUS=""
WARMUP_DURATION="0s"

# ============================================================================
# CLEANUP
# ============================================================================

cleanup() {
    local exit_code=$?
    stop_docker_stats_collection 2>/dev/null || true
    cleanup_service
    exit $exit_code
}

trap cleanup EXIT INT TERM

# ============================================================================
# CONFIGURATION
# ============================================================================

load_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "Configuration file not found: $CONFIG_FILE"
        exit 1
    fi

    DEFAULT_SERVICE_TYPE=$(jq -r '.default_settings.service_type // "basic"' "$CONFIG_FILE")
    DEFAULT_TEST_MODE=$(jq -r '.default_settings.test_mode // "standard"' "$CONFIG_FILE")
    DEFAULT_SCENARIO=$(jq -r '.default_settings.scenario // "default"' "$CONFIG_FILE")
    DEFAULT_COLLECT_METRICS=$(jq -r '.default_settings.collect_metrics // true' "$CONFIG_FILE")
    DEFAULT_WAIT_TIMEOUT=$(jq -r '.default_settings.wait_timeout // 60' "$CONFIG_FILE")
    DEFAULT_EXPORT_FORMATS=$(jq -r '.default_settings.export_formats // ["json"] | join(",")' "$CONFIG_FILE")
}

get_service_config() {
    local service_type="$1"
    jq -r ".service_types.\"$service_type\"" "$CONFIG_FILE"
}

get_test_mode_config() {
    local test_mode="$1"
    jq -r ".test_modes.\"$test_mode\"" "$CONFIG_FILE"
}

list_services() {
    print_section "Available Services"
    jq -r '.service_types | to_entries[] | "  \(.key): \(.value.description // "No description")"' "$CONFIG_FILE"
}

list_test_modes() {
    print_section "Available Test Modes"
    jq -r '.test_modes | to_entries[] | "  \(.key): \(.value.description // "No description") (duration: \(.value.duration), vus: \(.value.vus), warmup: \(.value.warmup // "0s"))"' "$CONFIG_FILE"
}

show_config() {
    print_section "Current Configuration"
    echo "Config file: $CONFIG_FILE"
    echo
    jq '.' "$CONFIG_FILE"
}

# ============================================================================
# USAGE
# ============================================================================

usage() {
    cat << EOF
Load Testing Framework for Service Extensions

Usage: $(basename "$0") [OPTIONS]

Options:
  -s, --service SERVICE    Service type to test (required)
  -m, --mode MODE          Test mode (required)
  -n, --scenario SCENARIO  Test scenario (default: default)
  -d, --duration DURATION  Override test duration
  -v, --vus VUS            Override virtual users count
  -w, --warmup DURATION    Override warmup duration
  -c, --collect-metrics    Collect Docker metrics (default: true)
  -e, --export FORMATS     Export formats: json,prometheus,influxdb (comma-separated)
  -k, --keep-service       Keep service running after test
  --compare DIR1 DIR2      Compare two test runs
  -l, --list-services      List available services
  -L, --list-modes         List available test modes
  -S, --show-config        Show current configuration
  -h, --help               Show this help message

Examples:
  # Run quick test for java_basic
  $(basename "$0") -s java_basic -m quick

  # Run with Prometheus export
  $(basename "$0") -s java_basic -m standard -e json,prometheus

  # Compare two test runs
  $(basename "$0") --compare results/run1 results/run2

  # Run with custom warmup
  $(basename "$0") -s go_basic -m quick -w 5s
EOF
}

# ============================================================================
# REQUEST DATA BUILDING
# ============================================================================

build_grpc_request_data() {
    local service_config="$1"
    local scenario="$2"

    local request_data
    if [ "$scenario" != "default" ]; then
        request_data=$(echo "$service_config" | jq -r ".scenarios.\"$scenario\".request_data // .request_data // {}")
    else
        request_data=$(echo "$service_config" | jq -r '.request_data // {}')
    fi

    local request_type=$(echo "$request_data" | jq -r '.type // "headers_only"')
    local headers_data=$(echo "$request_data" | jq -r '.headers // {}')
    local body_data=$(echo "$request_data" | jq -r '.body // {}')
    local end_of_stream=$(echo "$request_data" | jq -r '.end_of_stream // true')

    local grpc_request_data
    case "$request_type" in
        "combined"|"headers_and_body")
            grpc_request_data=$(jq -n \
                --argjson headers "$headers_data" \
                --argjson body "$body_data" \
                --argjson eos "$end_of_stream" \
                '{
                    request_headers: {
                        headers: $headers,
                        end_of_stream: $eos
                    }
                }')
            ;;
        "body_only")
            grpc_request_data=$(jq -n \
                --argjson body "$body_data" \
                '{
                    request_body: $body
                }')
            ;;
        *)
            grpc_request_data=$(jq -n \
                --argjson headers "$headers_data" \
                --argjson eos "$end_of_stream" \
                '{
                    request_headers: {
                        headers: $headers,
                        end_of_stream: $eos
                    }
                }')
            ;;
    esac

    echo "$grpc_request_data"
}

# ============================================================================
# WARMUP
# ============================================================================

run_warmup() {
    local warmup_duration="$1"
    local container_port="$2"
    local request_file="$3"

    if [ "$warmup_duration" = "0" ] || [ "$warmup_duration" = "0s" ]; then
        return 0
    fi

    log_info "Running warmup phase (${warmup_duration})..."
    
    # Run a short warmup with ghz (results discarded)
    ghz --insecure \
        --proto "$SCRIPT_DIR/proto/envoy/service/ext_proc/v3/external_processor.proto" \
        --import-paths "$SCRIPT_DIR/proto" \
        --call "envoy.service.ext_proc.v3.ExternalProcessor/Process" \
        --data-file "$request_file" \
        --concurrency=5 \
        --duration="${warmup_duration}" \
        "ext-proc-service:${container_port}" >/dev/null 2>&1 || true

    log_success "Warmup completed"
    sleep 1
}

# ============================================================================
# TEST EXECUTION
# ============================================================================

run_load_test() {
    local service_type="$1"
    local test_mode="$2"
    local scenario="${3:-default}"
    local duration="${4:-}"
    local vus="${5:-}"
    local warmup="${6:-}"
    local collect_metrics="${7:-$DEFAULT_COLLECT_METRICS}"
    local keep_service="${8:-false}"
    local export_formats="${9:-$DEFAULT_EXPORT_FORMATS}"

    local service_config=$(get_service_config "$service_type")
    local test_mode_config=$(get_test_mode_config "$test_mode")

    if [ "$service_config" = "null" ]; then
        log_error "Unknown service type: $service_type"
        list_services
        exit 1
    fi

    if [ "$test_mode_config" = "null" ]; then
        log_error "Unknown test mode: $test_mode"
        list_test_modes
        exit 1
    fi

    # Get test parameters
    TEST_DURATION="${duration:-$(echo "$test_mode_config" | jq -r '.duration')}"
    TEST_VUS="${vus:-$(echo "$test_mode_config" | jq -r '.vus')}"
    WARMUP_DURATION="${warmup:-$(echo "$test_mode_config" | jq -r '.warmup // "0s"')}"

    local container_port=$(echo "$service_config" | jq -r '.container_port // .port // "8080"')
    local health_port=$(echo "$service_config" | jq -r '.health_check_port // "80"')

    print_section "Load Test: $service_type/$test_mode/$scenario"
    log_info "Duration: $TEST_DURATION, VUs: $TEST_VUS, Warmup: $WARMUP_DURATION"

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local test_run_dir="${service_type}_${test_mode}_${scenario}_${timestamp}"
    local file_prefix="${service_type}_${test_mode}_${scenario}_${timestamp}"
    RESULTS_DIR="$SCRIPT_DIR/results/$test_run_dir"

    log_info "Results directory: $test_run_dir"

    # Start service
    SERVICE_CONTAINER_ID=$(start_service_container "$service_type" "$scenario" "$service_config")
    
    if ! wait_for_healthy "$health_port" "$DEFAULT_WAIT_TIMEOUT"; then
        exit 1
    fi

    # Build request data
    local grpc_request_data=$(build_grpc_request_data "$service_config" "$scenario")

    mkdir -p "$RESULTS_DIR"

    # Save request data
    local request_file="$RESULTS_DIR/${file_prefix}_request.json"
    echo "$grpc_request_data" > "$request_file"
    log_info "Request data saved to: $request_file"

    # Start metrics collection
    if [ "$collect_metrics" = "true" ]; then
        local duration_seconds="${TEST_DURATION%s}"
        local warmup_seconds="${WARMUP_DURATION%s}"
        local stats_duration=$((duration_seconds + warmup_seconds + 10))
        start_docker_stats_collection "$SERVICE_CONTAINER_ID" "$stats_duration" 2 "$RESULTS_DIR/${file_prefix}_docker_stats.json"
        sleep 2
    fi

    # Run warmup
    run_warmup "$WARMUP_DURATION" "$container_port" "$request_file"

    # Run load test
    log_info "Running load test with ghz..."
    local test_start=$(date +%s)
    local duration_seconds="${TEST_DURATION%s}"
    local ghz_exit_code=0
    local ghz_stderr_file="$RESULTS_DIR/${file_prefix}_ghz_stderr.log"

    ghz --insecure \
        --proto "$SCRIPT_DIR/proto/envoy/service/ext_proc/v3/external_processor.proto" \
        --import-paths "$SCRIPT_DIR/proto" \
        --call "envoy.service.ext_proc.v3.ExternalProcessor/Process" \
        --data-file "$request_file" \
        --concurrency="$TEST_VUS" \
        --duration="${duration_seconds}s" \
        --format=json \
        --output="$RESULTS_DIR/${file_prefix}_ghz_results.json" \
        "ext-proc-service:${container_port}" 2>"$ghz_stderr_file" || ghz_exit_code=$?

    local test_end=$(date +%s)
    local test_duration=$((test_end - test_start))
    
    if [ $ghz_exit_code -ne 0 ]; then
        log_warning "ghz exited with code $ghz_exit_code"
        if [ -s "$ghz_stderr_file" ]; then
            log_warning "ghz stderr output:"
            cat "$ghz_stderr_file" >&2
        fi
    else
        rm -f "$ghz_stderr_file"
    fi
    
    log_success "Load test completed in ${test_duration}s"

    # Stop metrics collection and analyze
    if [ "$collect_metrics" = "true" ]; then
        sleep 2
        stop_docker_stats_collection
        finalize_docker_stats "$RESULTS_DIR/${file_prefix}_docker_stats.json"
        analyze_docker_stats "$file_prefix" "$RESULTS_DIR" || true
        analyze_ghz_results "$file_prefix" "$RESULTS_DIR" || true
    fi

    # Export metrics in requested formats
    IFS=',' read -ra FORMATS <<< "$export_formats"
    for format in "${FORMATS[@]}"; do
        case "$format" in
            prometheus)
                export_prometheus "$file_prefix" "$RESULTS_DIR" "$service_type" "$test_mode"
                ;;
            influxdb)
                export_influxdb "$file_prefix" "$RESULTS_DIR" "$service_type" "$test_mode"
                ;;
            json)
                # JSON is always exported (default)
                ;;
        esac
    done

    # Generate report
    if [ -f "$RESULTS_DIR/${file_prefix}_ghz_results.json" ]; then
        generate_markdown_report "$service_type" "$test_mode" "$scenario" "$file_prefix" "$RESULTS_DIR" "$TEST_DURATION" "$TEST_VUS" "$WARMUP_DURATION"
    fi

    # Create latest symlink
    ln -sfn "$test_run_dir" "$SCRIPT_DIR/results/latest"
    log_info "Results available at: results/$test_run_dir"
    log_info "Latest results symlink: results/latest"

    if [ "$keep_service" = "true" ]; then
        log_info "Service kept running (ID: $SERVICE_CONTAINER_ID)"
        trap - EXIT INT TERM
        SERVICE_CONTAINER_ID=""
    fi
}

# ============================================================================
# COMPARISON
# ============================================================================

run_comparison() {
    local dir1="$1"
    local dir2="$2"

    print_section "Comparing Test Runs"
    log_info "Run 1: $dir1"
    log_info "Run 2: $dir2"

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local comparison_dir="$SCRIPT_DIR/results/comparison_${timestamp}"
    mkdir -p "$comparison_dir"

    compare_runs "$dir1" "$dir2" "$comparison_dir/comparison.json"
    generate_comparison_report "$comparison_dir/comparison.json" "$comparison_dir/comparison_report.md"

    log_info "Comparison results: $comparison_dir"
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    local service_type=""
    local test_mode=""
    local scenario=""
    local duration=""
    local vus=""
    local warmup=""
    local collect_metrics="$DEFAULT_COLLECT_METRICS"
    local keep_service="false"
    local export_formats="$DEFAULT_EXPORT_FORMATS"
    local compare_dir1=""
    local compare_dir2=""

    load_config

    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--service)
                service_type="$2"
                shift 2
                ;;
            -m|--mode)
                test_mode="$2"
                shift 2
                ;;
            -n|--scenario)
                scenario="$2"
                shift 2
                ;;
            -d|--duration)
                duration="$2"
                shift 2
                ;;
            -v|--vus)
                vus="$2"
                shift 2
                ;;
            -w|--warmup)
                warmup="$2"
                shift 2
                ;;
            -c|--collect-metrics)
                collect_metrics="true"
                shift
                ;;
            -e|--export)
                export_formats="$2"
                shift 2
                ;;
            -k|--keep-service)
                keep_service="true"
                shift
                ;;
            --compare)
                compare_dir1="$2"
                compare_dir2="$3"
                shift 3
                ;;
            -l|--list-services)
                list_services
                exit 0
                ;;
            -L|--list-modes)
                list_test_modes
                exit 0
                ;;
            -S|--show-config)
                show_config
                exit 0
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Handle comparison mode
    if [ -n "$compare_dir1" ] && [ -n "$compare_dir2" ]; then
        run_comparison "$compare_dir1" "$compare_dir2"
        exit 0
    fi

    # Validate required parameters for test mode
    if [ -z "$service_type" ] || [ -z "$test_mode" ]; then
        log_error "Service type (-s) and test mode (-m) are required"
        usage
        exit 1
    fi

    run_load_test "$service_type" "$test_mode" "${scenario:-$DEFAULT_SCENARIO}" \
        "$duration" "$vus" "$warmup" "$collect_metrics" "$keep_service" "$export_formats"
}

main "$@"
