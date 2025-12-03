#!/bin/bash
# Load Testing Framework for Service Extensions
# Supports multiple service types, test modes, and export formats

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# DEPENDENCY CHECKS
# ============================================================================

# Check for required dependencies
check_dependencies() {
    local missing_deps=()
    
    # Required tools
    command -v docker >/dev/null 2>&1 || missing_deps+=("docker")
    command -v jq >/dev/null 2>&1 || missing_deps+=("jq")
    command -v curl >/dev/null 2>&1 || missing_deps+=("curl")
    command -v bc >/dev/null 2>&1 || missing_deps+=("bc")
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo "[ERROR] Missing required dependencies: ${missing_deps[*]}" >&2
        echo "[ERROR] Please install them before running this script." >&2
        echo "" >&2
        echo "On Alpine: apk add ${missing_deps[*]}" >&2
        echo "On Debian/Ubuntu: apt-get install ${missing_deps[*]}" >&2
        echo "On macOS: brew install ${missing_deps[*]}" >&2
        exit 1
    fi
}

# Run dependency check early (before sourcing libs that might use these tools)
check_dependencies

# Load configuration
CONFIG_FILE="${CONFIG_FILE:-$SCRIPT_DIR/config/test-config.json}"
RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"

# Dynamically discover the Docker network (supports any directory name)
discover_network() {
    local network
    network=$(docker network ls --filter "label=com.service-extensions.load-testing=true" --format "{{.Name}}" 2>/dev/null | head -1)
    if [ -z "$network" ]; then
        # Fallback: try common patterns
        network=$(docker network ls --format "{{.Name}}" 2>/dev/null | grep -E "load-test.*network|load-testing.*network" | head -1)
    fi
    echo "${network:-load-testing_load-test-network}"
}
NETWORK_NAME="${NETWORK_NAME:-$(discover_network)}"

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
# DURATION UTILITIES
# ============================================================================

# Convert duration string to seconds
# Supports: seconds (s), minutes (m), hours (h)
# Examples: "10s" -> 10, "5m" -> 300, "1h" -> 3600, "90" -> 90
# Returns: seconds as integer, or empty string on error
duration_to_seconds() {
    local duration="$1"
    local value
    local unit
    local result
    
    # If empty or zero, return 0
    if [ -z "$duration" ] || [ "$duration" = "0" ] || [ "$duration" = "0s" ]; then
        echo "0"
        return 0
    fi
    
    # Strict format validation: must be <number>[unit] where unit is optional
    # Valid patterns: "30", "30s", "5m", "1h", "5.5m", "1.5h"
    # Also allow longer unit names: "min", "mins", "minute", "minutes", "sec", etc.
    # Pattern: digits (with optional decimal), followed by optional unit letters only at the end
    if ! [[ "$duration" =~ ^[0-9]+\.?[0-9]*[a-zA-Z]*$ ]]; then
        echo ""
        return 1
    fi
    
    # Additional validation: unit must be at the end (no digits after letters)
    # This catches cases like "5m5" or "1h30m"
    if [[ "$duration" =~ [a-zA-Z][0-9] ]]; then
        echo ""
        return 1
    fi
    
    # Extract numeric value (everything before letters) and unit (letters at end)
    value=$(echo "$duration" | sed 's/[a-zA-Z]*$//')
    unit=$(echo "$duration" | sed 's/^[0-9.]*//' | tr '[:upper:]' '[:lower:]')
    
    # If no value found, return empty (error)
    if [ -z "$value" ]; then
        echo ""
        return 1
    fi
    
    # Validate value is a valid number
    if ! [[ "$value" =~ ^[0-9]+\.?[0-9]*$ ]]; then
        echo ""
        return 1
    fi
    
    # Convert based on unit
    case "$unit" in
        "h"|"hr"|"hrs"|"hour"|"hours")
            result=$(echo "$value * 3600" | bc 2>/dev/null | cut -d. -f1)
            ;;
        "m"|"min"|"mins"|"minute"|"minutes")
            result=$(echo "$value * 60" | bc 2>/dev/null | cut -d. -f1)
            ;;
        "s"|"sec"|"secs"|"second"|"seconds"|"")
            result=$(echo "$value" | cut -d. -f1)
            ;;
        *)
            # Unknown unit - return empty
            echo ""
            return 1
            ;;
    esac
    
    # Validate result is a positive integer
    if [ -z "$result" ] || ! [[ "$result" =~ ^[0-9]+$ ]]; then
        echo ""
        return 1
    fi
    
    echo "$result"
    return 0
}

# Validate duration and exit with error message if invalid
# Usage: validate_duration "10s" "duration" || exit 1
validate_duration() {
    local duration="$1"
    local name="${2:-duration}"
    local seconds
    
    seconds=$(duration_to_seconds "$duration")
    
    if [ -z "$seconds" ]; then
        log_error "Invalid $name format: '$duration'"
        log_error "Supported formats: 30s (seconds), 5m (minutes), 1h (hours)"
        return 1
    fi
    
    echo "$seconds"
    return 0
}

# Format seconds back to a human-readable duration string
seconds_to_duration() {
    local seconds="$1"
    if [ "$seconds" -ge 3600 ]; then
        echo "$((seconds / 3600))h"
    elif [ "$seconds" -ge 60 ]; then
        echo "$((seconds / 60))m"
    else
        echo "${seconds}s"
    fi
}

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
  -d, --duration DURATION  Override test duration (supports: 30s, 5m, 1h)
  -v, --vus VUS            Override virtual users count
  -w, --warmup DURATION    Override warmup duration (supports: 30s, 5m, 1h)
  -c, --collect-metrics    Collect Docker metrics (default: true)
  -e, --export FORMATS     Export formats: json,prometheus,influxdb (comma-separated)
  -k, --keep-service       Keep service running after test
  --compare DIR1 DIR2      Compare two test runs
  -l, --list-services      List available services
  -L, --list-modes         List available test modes
  -S, --show-config        Show current configuration
  -h, --help               Show this help message

Duration Formats:
  Seconds:  30s, 60s, 120s (or just 30, 60, 120)
  Minutes:  5m, 10m, 30m
  Hours:    1h, 2h

Examples:
  # Run quick test for python_basic
  $(basename "$0") -s python_basic -m quick

  # Run with Prometheus export
  $(basename "$0") -s python_basic -m standard -e json,prometheus

  # Compare two test runs
  $(basename "$0") --compare results/run1 results/run2

  # Run with custom warmup (30 seconds)
  $(basename "$0") -s python_basic -m quick -w 30s

  # Run 5 minute test with 2 minute warmup
  $(basename "$0") -s python_basic -m quick -d 5m -w 2m

  # Run 1 hour soak test
  $(basename "$0") -s python_basic -m soak -d 1h
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
        "request_headers")
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
        "request_body")
            grpc_request_data=$(jq -n \
                --argjson body "$body_data" \
                --argjson eos "$end_of_stream" \
                '{
                    request_body: {
                        body: ($body.body // $body | if type == "string" then @base64 else . end),
                        end_of_stream: $eos
                    }
                }')
            ;;
        "request_combined")
            grpc_request_data=$(jq -n \
                --argjson headers "$headers_data" \
                --argjson body "$body_data" \
                --argjson eos "$end_of_stream" \
                '{
                    request_headers: {
                        headers: $headers,
                        end_of_stream: false
                    },
                    request_body: {
                        body: ($body.body // $body | if type == "string" then @base64 else . end),
                        end_of_stream: $eos
                    }
                }')
            ;;
        "response_headers")
            grpc_request_data=$(jq -n \
                --argjson headers "$headers_data" \
                --argjson eos "$end_of_stream" \
                '{
                    response_headers: {
                        headers: $headers,
                        end_of_stream: $eos
                    }
                }')
            ;;
        "response_body")
            grpc_request_data=$(jq -n \
                --argjson body "$body_data" \
                --argjson eos "$end_of_stream" \
                '{
                    response_body: {
                        body: ($body.body // $body | if type == "string" then @base64 else . end),
                        end_of_stream: $eos
                    }
                }')
            ;;
        "response_combined")
            grpc_request_data=$(jq -n \
                --argjson headers "$headers_data" \
                --argjson body "$body_data" \
                --argjson eos "$end_of_stream" \
                '{
                    response_headers: {
                        headers: $headers,
                        end_of_stream: false
                    },
                    response_body: {
                        body: ($body.body // $body | if type == "string" then @base64 else . end),
                        end_of_stream: $eos
                    }
                }')
            ;;
        *)
            # Default: request_headers
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
    local health_check_container_port=$(echo "$service_config" | jq -r '.health_check_container_port // "80"')

    print_section "Load Test: $service_type/$test_mode/$scenario"
    log_info "Duration: $TEST_DURATION, VUs: $TEST_VUS, Warmup: $WARMUP_DURATION"

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local test_run_dir="${service_type}_${test_mode}_${scenario}_${timestamp}"
    local file_prefix="${service_type}_${test_mode}_${scenario}_${timestamp}"
    RESULTS_DIR="$SCRIPT_DIR/results/$test_run_dir"

    log_info "Results directory: $test_run_dir"

    # Start service
    SERVICE_CONTAINER_ID=$(start_service_container "$service_type" "$scenario" "$service_config")
    
    # Verify we got a valid container ID (64-char hex string)
    if [ -z "$SERVICE_CONTAINER_ID" ] || [ ${#SERVICE_CONTAINER_ID} -ne 64 ]; then
        # Fallback: get the container ID from docker ps using the name pattern
        log_warning "Container ID capture may have failed, looking up by name..."
        SERVICE_CONTAINER_ID=$(docker ps --filter "name=ext-proc-service-test-" --format "{{.ID}}" | head -1)
        if [ -z "$SERVICE_CONTAINER_ID" ]; then
            log_error "Failed to determine container ID"
            exit 1
        fi
    fi
    
    log_info "Service container ID: ${SERVICE_CONTAINER_ID:0:12}..."
    
    if ! wait_for_healthy "$health_check_container_port" "$DEFAULT_WAIT_TIMEOUT"; then
        exit 1
    fi

    # Build request data
    local grpc_request_data=$(build_grpc_request_data "$service_config" "$scenario")

    mkdir -p "$RESULTS_DIR"

    # Save request data
    local request_file="$RESULTS_DIR/${file_prefix}_request.json"
    echo "$grpc_request_data" > "$request_file"
    log_info "Request data saved to: $request_file"

    # Convert durations to seconds (supports s/m/h formats)
    # validate_duration returns the seconds value or exits with error
    local duration_seconds
    local warmup_seconds
    
    duration_seconds=$(validate_duration "$TEST_DURATION" "test duration")
    if [ $? -ne 0 ] || [ -z "$duration_seconds" ]; then
        log_error "Failed to parse test duration: '$TEST_DURATION'"
        exit 1
    fi
    
    warmup_seconds=$(validate_duration "$WARMUP_DURATION" "warmup duration")
    if [ $? -ne 0 ] || [ -z "$warmup_seconds" ]; then
        log_error "Failed to parse warmup duration: '$WARMUP_DURATION'"
        exit 1
    fi
    
    log_info "Test duration: ${duration_seconds}s, Warmup: ${warmup_seconds}s"

    # Start metrics collection
    if [ "$collect_metrics" = "true" ]; then
        local stats_duration=$((duration_seconds + warmup_seconds + 10))
        start_docker_stats_collection "$SERVICE_CONTAINER_ID" "$stats_duration" 2 "$RESULTS_DIR/${file_prefix}_docker_stats.json"
        sleep 2
    fi

    # Run warmup
    run_warmup "${warmup_seconds}s" "$container_port" "$request_file"

    # Run load test
    log_info "Running load test with ghz..."
    local test_start=$(date +%s)
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

    # Analyze ghz results (always needed for exports and reports)
    analyze_ghz_results "$file_prefix" "$RESULTS_DIR" || true

    # Stop metrics collection and analyze Docker stats (only if metrics collection enabled)
    if [ "$collect_metrics" = "true" ]; then
        sleep 2
        stop_docker_stats_collection
        finalize_docker_stats "$RESULTS_DIR/${file_prefix}_docker_stats.json"
        analyze_docker_stats "$file_prefix" "$RESULTS_DIR" || true
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
        SERVICE_CONTAINER_NAME=""
    else
        # Explicitly cleanup after report generation if not keeping service
        log_info "Cleaning up service container after test completion..."
        cleanup_service
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
