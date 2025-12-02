#!/bin/bash
# Docker management functions for load testing framework

# Global variables
SERVICE_CONTAINER_ID=""
DOCKER_STATS_PID=""
NETWORK_NAME="${NETWORK_NAME:-load-testing_load-test-network}"

# Start the service container
start_service_container() {
    local service_type="$1"
    local scenario="$2"
    local service_config="$3"

    local image=$(echo "$service_config" | jq -r '.image')
    local host_port=$(echo "$service_config" | jq -r '.port')
    local container_port=$(echo "$service_config" | jq -r '.container_port // .port // "8080"')
    local health_port=$(echo "$service_config" | jq -r '.health_check_port // .container_port // .port // "80"')
    
    # Parse command array safely using mapfile
    local -a command_args=()
    if [ "$(echo "$service_config" | jq -r '.command | length')" -gt 0 ]; then
        mapfile -t command_args < <(echo "$service_config" | jq -r '.command[]')
    fi

    local cpu_limit=$(echo "$service_config" | jq -r '.resources.cpu_limit // "2.0"')
    local memory_limit=$(echo "$service_config" | jq -r '.resources.memory_limit // "512m"')
    local cpu_reservation=$(echo "$service_config" | jq -r '.resources.cpu_reservation // "0.5"')
    local memory_reservation=$(echo "$service_config" | jq -r '.resources.memory_reservation // "256m"')

    log_info "Starting ext-proc-service ($service_type/$scenario)..."
    log_info "Resource limits: CPU=${cpu_limit}, Memory=${memory_limit}"

    local docker_run_args=(
        -d
        --name "ext-proc-service-test-$$"
        --network "$NETWORK_NAME"
        --hostname ext-proc-service
        -e PYTHONUNBUFFERED=1
        -e SERVICE_TYPE="$service_type"
        -e SCENARIO="$scenario"
        -p "${host_port}:${container_port}"
        -p "${health_port}:${health_port}"
        --cpus="$cpu_limit"
        --memory="$memory_limit"
        --cpu-shares="$(echo "$cpu_reservation * 1024" | bc | cut -d. -f1)"
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

    if [ ${#command_args[@]} -gt 0 ]; then
        SERVICE_CONTAINER_ID=$(docker run "${docker_run_args[@]}" "$image" "${command_args[@]}")
    else
        SERVICE_CONTAINER_ID=$(docker run "${docker_run_args[@]}" "$image")
    fi

    echo "$SERVICE_CONTAINER_ID"
}

# Wait for service to be healthy
wait_for_healthy() {
    local health_port="$1"
    local max_wait="${2:-60}"
    
    log_info "Waiting for service to be healthy..."
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if curl -sf "http://ext-proc-service:${health_port}/" >/dev/null 2>&1; then
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
    if [ -n "${SERVICE_CONTAINER_ID:-}" ]; then
        log_info "Cleaning up ext-proc-service container..."
        docker stop "$SERVICE_CONTAINER_ID" >/dev/null 2>&1 || true
        docker rm "$SERVICE_CONTAINER_ID" >/dev/null 2>&1 || true
    fi
}

# Collect Docker stats in background
start_docker_stats_collection() {
    local container_id="$1"
    local duration="$2"
    local interval="${3:-2}"
    local output_file="$4"

    log_info "Collecting Docker stats for ${duration}s (every ${interval}s)..."
    
    # Create temp file for raw stats
    local temp_file="${output_file}.tmp"
    echo -n "" > "$temp_file"
    echo "[]" > "$output_file"  # Initialize with empty array
    
    (
        local end_time=$(($(date +%s) + duration))
        local timestamp_counter=0
        
        while [ $(date +%s) -lt $end_time ]; do
            # Use container ID directly for reliable stats collection
            local stats=$(docker stats --no-stream --format '{"timestamp":'$timestamp_counter',"name":"{{.Name}}","cpu":"{{.CPUPerc}}","memory":"{{.MemPerc}}","mem_usage":"{{.MemUsage}}","net_io":"{{.NetIO}}","block_io":"{{.BlockIO}}"}' "$container_id" 2>/dev/null)
            if [ -n "$stats" ]; then
                echo "$stats" >> "$temp_file"
                timestamp_counter=$((timestamp_counter + interval))
            fi
            sleep "$interval"
        done
    ) &
    DOCKER_STATS_PID=$!
    log_info "Docker stats collection started (PID: $DOCKER_STATS_PID)"
}

# Finalize Docker stats collection
finalize_docker_stats() {
    local output_file="$1"
    local temp_file="${output_file}.tmp"
    
    if [ -f "$temp_file" ] && [ -s "$temp_file" ]; then
        # Convert line-separated JSON to array
        local json_content=$(cat "$temp_file" | paste -sd ',' -)
        echo "[$json_content]" > "$output_file"
        rm -f "$temp_file"
    else
        echo "[]" > "$output_file"
        rm -f "$temp_file" 2>/dev/null || true
    fi
}

# Stop Docker stats collection
stop_docker_stats_collection() {
    if [ -n "${DOCKER_STATS_PID:-}" ]; then
        kill "$DOCKER_STATS_PID" 2>/dev/null || true
        wait "$DOCKER_STATS_PID" 2>/dev/null || true
        log_info "Docker stats collection stopped"
    fi
}

