#!/bin/bash
# Docker management functions for load testing framework

# Global variables
SERVICE_CONTAINER_ID=""
SERVICE_CONTAINER_NAME=""
DOCKER_STATS_PID=""

# Calculate CPU shares from reservation value (e.g., "0.5" -> 512, "1.0" -> 1024)
# Uses bc if available, falls back to awk for portability
_calc_cpu_shares() {
    local cpu_reservation="$1"
    local shares
    
    if command -v bc >/dev/null 2>&1; then
        shares=$(echo "$cpu_reservation * 1024" | bc 2>/dev/null | cut -d. -f1)
    else
        # Fallback using awk (more portable)
        shares=$(awk "BEGIN {printf \"%.0f\", $cpu_reservation * 1024}")
    fi
    
    # Default to 512 if calculation fails
    echo "${shares:-512}"
}

# Dynamically discover the Docker network (supports any directory name)
# The network is labeled in docker-compose.yml for reliable discovery
_discover_network() {
    local network
    network=$(docker network ls --filter "label=com.service-extensions.load-testing=true" --format "{{.Name}}" 2>/dev/null | head -1)
    if [ -z "$network" ]; then
        # Fallback: try common patterns
        network=$(docker network ls --format "{{.Name}}" 2>/dev/null | grep -E "load-test.*network|load-testing.*network" | head -1)
    fi
    echo "${network:-load-testing_load-test-network}"
}
NETWORK_NAME="${NETWORK_NAME:-$(_discover_network)}"

# Start the service container
start_service_container() {
    local service_type="$1"
    local scenario="$2"
    local service_config="$3"

    local image=$(echo "$service_config" | jq -r '.image')
    local host_port=$(echo "$service_config" | jq -r '.port')
    local container_port=$(echo "$service_config" | jq -r '.container_port // "8080"')
    local health_check_host_port=$(echo "$service_config" | jq -r '.health_check_port // "80"')
    local health_check_container_port=$(echo "$service_config" | jq -r '.health_check_container_port // "80"')
    
    # Parse command array safely using mapfile
    local -a command_args=()
    if [ "$(echo "$service_config" | jq -r '.command | length')" -gt 0 ]; then
        mapfile -t command_args < <(echo "$service_config" | jq -r '.command[]')
    fi

    local cpu_limit=$(echo "$service_config" | jq -r '.resources.cpu_limit // "2.0"')
    local memory_limit=$(echo "$service_config" | jq -r '.resources.memory_limit // "512m"')
    local cpu_reservation=$(echo "$service_config" | jq -r '.resources.cpu_reservation // "0.5"')
    local memory_reservation=$(echo "$service_config" | jq -r '.resources.memory_reservation // "256m"')

    log_info "Starting ext-proc-service ($service_type/$scenario)..." >&2
    log_info "Resource limits: CPU=${cpu_limit}, Memory=${memory_limit}" >&2

    local docker_run_args=(
        -d
        --name "ext-proc-service-test-$$"
        --network "$NETWORK_NAME"
        --hostname ext-proc-service
        -e PYTHONUNBUFFERED=1
        -e SERVICE_TYPE="$service_type"
        -e SCENARIO="$scenario"
        -p "${host_port}:${container_port}"
        -p "${health_check_host_port}:${health_check_container_port}"
        --cpus="$cpu_limit"
        --memory="$memory_limit"
        --cpu-shares="$(_calc_cpu_shares "$cpu_reservation")"
        --memory-reservation="$memory_reservation"
    )

    # Add custom environment variables from config
    local env_keys=$(echo "$service_config" | jq -r '.env // {} | keys[]' 2>/dev/null)
    if [ -n "$env_keys" ]; then
        while IFS= read -r key; do
            local value=$(echo "$service_config" | jq -r ".env.\"$key\"")
            docker_run_args+=("-e" "${key}=${value}")
        done <<< "$env_keys"
    fi

    local container_name="ext-proc-service-test-$$"
    SERVICE_CONTAINER_NAME="$container_name"
    
    if [ ${#command_args[@]} -gt 0 ]; then
        SERVICE_CONTAINER_ID=$(docker run "${docker_run_args[@]}" "$image" "${command_args[@]}")
    else
        SERVICE_CONTAINER_ID=$(docker run "${docker_run_args[@]}" "$image")
    fi

    echo "$SERVICE_CONTAINER_ID"
}

# Wait for service to be healthy
wait_for_healthy() {
    local health_check_container_port="$1"
    local max_wait="${2:-60}"
    
    log_info "Waiting for service to be healthy..."
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if curl -sf "http://ext-proc-service:${health_check_container_port}/" >/dev/null 2>&1; then
            log_success "Service is healthy!"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done

    log_error "Service failed to become healthy after ${max_wait}s"
    docker logs "$SERVICE_CONTAINER_ID" 2>&1 | tail -20
    return 1
}

# Cleanup service container
cleanup_service() {
    log_info "Cleaning up ext-proc-service container..."
    
    # Try cleanup by container ID first
    if [ -n "${SERVICE_CONTAINER_ID:-}" ]; then
        docker stop "$SERVICE_CONTAINER_ID" >/dev/null 2>&1 || true
        docker rm "$SERVICE_CONTAINER_ID" >/dev/null 2>&1 || true
    fi
    
    # Also try cleanup by container name
    if [ -n "${SERVICE_CONTAINER_NAME:-}" ]; then
        docker stop "$SERVICE_CONTAINER_NAME" >/dev/null 2>&1 || true
        docker rm "$SERVICE_CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
    
    # Fallback: cleanup any containers matching the pattern
    docker ps -a --filter "name=ext-proc-service-test-" --format "{{.ID}}" 2>/dev/null | while read -r container_id; do
        if [ -n "$container_id" ]; then
            docker stop "$container_id" >/dev/null 2>&1 || true
            docker rm "$container_id" >/dev/null 2>&1 || true
        fi
    done
}

# Collect Docker stats in background
start_docker_stats_collection() {
    local container_identifier="$1"
    local duration="$2"
    local interval="${3:-2}"
    local output_file="$4"

    log_info "Collecting Docker stats for ${duration}s (every ${interval}s)..."
    
    # Create temp file for raw stats
    local temp_file="${output_file}.tmp"
    echo -n "" > "$temp_file"
    echo "[]" > "$output_file"  # Initialize with empty array
    
    # Use container ID directly
    local container_ref="$container_identifier"
    
    # Verify container exists and is running before starting collection
    local container_exists=false
    if docker inspect "$container_ref" >/dev/null 2>&1; then
        # Check if container is running - match by full ID or short ID prefix
        if docker ps --format '{{.ID}}' | grep -qE "^${container_ref}|^${container_ref:0:12}" 2>/dev/null; then
            container_exists=true
            log_info "Container verified for stats collection: ${container_ref:0:12}..."
        else
            log_warning "Container ${container_ref:0:12}... exists but is not running. Stats collection may fail."
            log_info "Checking container status..."
            docker ps -a --filter "id=${container_ref:0:12}" --format "{{.ID}} {{.Status}}" 2>/dev/null || true
        fi
    else
        log_warning "Container '$container_ref' not found. Stats collection may fail."
        log_info "Available running containers: $(docker ps --format '{{.ID}} ({{.Names}})' | head -5 | tr '\n' ' ')"
    fi
    
    (
        local end_time=$(($(date +%s) + duration))
        local timestamp_counter=0
        local stats_count=0
        local error_count=0
        
        while [ $(date +%s) -lt $end_time ]; do
            # Check if container still exists and is running before collecting stats
            if ! docker inspect "$container_ref" >/dev/null 2>&1 || \
               ! docker ps --format '{{.ID}}' | grep -qE "^${container_ref}|^${container_ref:0:12}" 2>/dev/null; then
                error_count=$((error_count + 1))
                if [ $((error_count % 10)) -eq 1 ]; then
                    echo "[DEBUG] Container '${container_ref:0:12}...' no longer exists or is not running" >> "$temp_file.errors" 2>&1 || true
                fi
                sleep "$interval"
                continue
            fi
            
            # Try collecting stats - use short ID if long ID fails
            local stats_output=""
            local exit_code=1
            
            # Try with full container ID first
            stats_output=$(docker stats --no-stream --format '{"timestamp":'$timestamp_counter',"name":"{{.Name}}","cpu":"{{.CPUPerc}}","memory":"{{.MemPerc}}","mem_usage":"{{.MemUsage}}","net_io":"{{.NetIO}}","block_io":"{{.BlockIO}}"}' "$container_ref" 2>&1)
            exit_code=$?
            
            # If that fails and we have a long ID, try short ID (first 12 chars)
            if [ $exit_code -ne 0 ] && [ ${#container_ref} -gt 12 ]; then
                local short_id="${container_ref:0:12}"
                stats_output=$(docker stats --no-stream --format '{"timestamp":'$timestamp_counter',"name":"{{.Name}}","cpu":"{{.CPUPerc}}","memory":"{{.MemPerc}}","mem_usage":"{{.MemUsage}}","net_io":"{{.NetIO}}","block_io":"{{.BlockIO}}"}' "$short_id" 2>&1)
                exit_code=$?
                if [ $exit_code -eq 0 ]; then
                    container_ref="$short_id"  # Use short ID for subsequent calls
                fi
            fi
            
            # Check if we got valid JSON with expected fields
            if [ $exit_code -eq 0 ] && [ -n "$stats_output" ]; then
                # Validate JSON structure - should contain cpu and memory fields
                if echo "$stats_output" | grep -qE '"cpu"[[:space:]]*:' && echo "$stats_output" | grep -qE '"memory"[[:space:]]*:'; then
                    echo "$stats_output" >> "$temp_file"
                    stats_count=$((stats_count + 1))
                    timestamp_counter=$((timestamp_counter + interval))
                else
                    error_count=$((error_count + 1))
                    if [ $((error_count % 10)) -eq 1 ]; then
                        echo "[DEBUG] Invalid JSON format: $stats_output" >> "$temp_file.errors" 2>&1 || true
                    fi
                fi
            else
                error_count=$((error_count + 1))
                # Only log errors occasionally to avoid spam, but log first few to diagnose
                if [ $error_count -le 3 ] || [ $((error_count % 10)) -eq 1 ]; then
                    echo "[DEBUG] Stats collection failed (exit: $exit_code, container: ${container_ref:0:12}..., error: ${stats_output:0:100})" >> "$temp_file.errors" 2>&1 || true
                fi
            fi
            sleep "$interval"
        done
        
        # Log summary to errors file
        echo "[SUMMARY] Collected $stats_count stats, $error_count errors" >> "$temp_file.errors" 2>&1 || true
    ) &
    DOCKER_STATS_PID=$!
    log_info "Docker stats collection started (PID: $DOCKER_STATS_PID) for container: ${SERVICE_CONTAINER_NAME:-$container_identifier}"
}

# Finalize Docker stats collection
finalize_docker_stats() {
    local output_file="$1"
    local temp_file="${output_file}.tmp"
    local error_file="${output_file}.tmp.errors"
    
    # Wait a moment for any final writes
    sleep 1
    
    if [ -f "$temp_file" ] && [ -s "$temp_file" ]; then
        # Convert line-separated JSON to array
        # Filter out any invalid JSON lines
        local valid_lines=$(grep -v '^[[:space:]]*$' "$temp_file" | grep -E '^\s*\{' || true)
        
        if [ -n "$valid_lines" ]; then
            local json_content=$(echo "$valid_lines" | paste -sd ',' -)
            echo "[$json_content]" > "$output_file"
            
            # Log success
            local count=$(echo "$valid_lines" | wc -l)
            log_info "Finalized Docker stats: $count records collected"
        else
            log_warning "No valid stats records found in temp file"
            echo "[]" > "$output_file"
        fi
        
        rm -f "$temp_file"
    else
        log_warning "Docker stats temp file is empty or missing: $temp_file"
        if [ -f "$error_file" ]; then
            log_info "Stats collection errors:"
            tail -5 "$error_file" 2>/dev/null || true
        fi
        echo "[]" > "$output_file"
    fi
    
    rm -f "$temp_file" "$error_file" 2>/dev/null || true
}

# Stop Docker stats collection
stop_docker_stats_collection() {
    if [ -n "${DOCKER_STATS_PID:-}" ]; then
        kill "$DOCKER_STATS_PID" 2>/dev/null || true
        wait "$DOCKER_STATS_PID" 2>/dev/null || true
        log_info "Docker stats collection stopped"
    fi
}

