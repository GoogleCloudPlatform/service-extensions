#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8080"
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Test scenarios: valid and invalid JWT tokens
TEST_SCENARIOS=("valid_jwt" "invalid_jwt")
VALID_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjE3MzQ2MSwiZXhwIjoyMDc1NjU4MjYxfQ.Vv-Lwn1z8BbVBGm-T1EKxv6T3XKCeRlvRrRmdu8USFdZUoSBK_aThzwzM2T8hlpReYsX9YFdJ3hMfq6OZTfHvfPLXvAt7iSKa03ZoPQzU8bRGzYy8xrb0ZQfrejGfHS5iHukzA8vtI2UAJ_9wFQiY5_VGHOBv9116efslbg-_gItJ2avJb0A0yr5uUwmE336rYEwgm4DzzfnTqPt8kcJwkONUsjEH__mePrva1qDT4qtfTPQpGa35TW8n9yZqse3h1w3xyxUfJd3BlDmoz6pQp2CvZkhdQpkWA1bnwpdqSDC7bHk4tYX6K5Q19na-2ff7gkmHZHJr0G9e_vAhQiE5w"
INVALID_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.invalid_signature"

REQUEST_DATA_VALID='{
  "request_headers": {
    "headers": {
      "headers": [
        {"key": "Authorization", "raw_value": "QmVhcmVyICVz"}
      ]
    },
    "end_of_stream": true
  }
}'

REQUEST_DATA_INVALID='{
  "request_headers": {
    "headers": {
      "headers": [
        {"key": "Authorization", "raw_value": "QmVhcmVyICVz"}
      ]
    },
    "end_of_stream": true
  }
}'

TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
OUTPUT_FILE="$SCRIPT_DIR/results/$(date +%Y%m%d_%H%M%S).json"

# Function to process test results
process_results() {
    local result_file=$1
    local scenario=$2
    
    if [ -f "$result_file" ]; then
        if command -v jq &> /dev/null; then
            local count=$(jq '.count' "$result_file")
            local total=$(jq '.total' "$result_file")
            local average=$(jq '.average' "$result_file")
            local rps=$(jq '.rps' "$result_file")
            
            # Get success/failure counts
            local ok_count=$(jq '.statusCodeDistribution.OK // 0' "$result_file")
            local denied_count=$(jq '.statusCodeDistribution.PERMISSION_DENIED // 0' "$result_file")
            
            # Convert nanoseconds to milliseconds
            local average_ms=$(echo "scale=2; $average / 1000000" | bc)
            
            # Calculate success percentage based on scenario
            if [ "$scenario" = "valid_jwt" ]; then
                success_rate=$(echo "scale=2; $ok_count * 100 / $count" | bc)
                printf "Scenario: %s | Avg latency: %sms | RPS: %s | Success rate: %s%%\n" \
                       "$scenario" "$average_ms" "$rps" "$success_rate"
                echo "Valid JWT - Header mutations applied: $ok_count"
            else
                success_rate=$(echo "scale=2; $denied_count * 100 / $count" | bc)
                printf "Scenario: %s | Avg latency: %sms | RPS: %s | Denial rate: %s%%\n" \
                       "$scenario" "$average_ms" "$rps" "$success_rate"
                echo "Invalid JWT - Requests denied: $denied_count"
            fi
        else
            echo "Install jq for detailed summary: sudo apt install jq"
            echo "Raw results: $result_file"
        fi
    else
        echo "Test results for $scenario not available"
    fi
}

# Function to recursively copy protos
copy_proto() {
    local proto_file=$1
    local target_path="$TEMP_PROTO_DIR/protodef/$proto_file"
    local src_path="$SRC_PROTO_DIR/$proto_file"
    
    # Skip Google protobuf files that are not present
    if [[ $proto_file == google/protobuf/* ]] && [ ! -f "$src_path" ]; then
        return 0
    fi
    
    # Check if source file exists
    if [ ! -f "$src_path" ]; then
        echo "Warning: File not found: $src_path (skipping)"
        return 0
    fi
    
    # Create directory structure
    mkdir -p "$(dirname "$target_path")"
    
    # Copy the file
    cp "$src_path" "$target_path"
    
    # Recursively copy dependencies
    grep '^import ' "$src_path" | while read -r line; do
        import_file=$(echo "$line" | sed -e 's/import "//' -e 's/";//')
        import_target="$TEMP_PROTO_DIR/protodef/$import_file"
        
        if [ ! -f "$import_target" ]; then
            mkdir -p "$(dirname "$import_target")"
            if [ -f "$SRC_PROTO_DIR/$import_file" ]; then
                cp "$SRC_PROTO_DIR/$import_file" "$import_target"
                copy_proto "$import_file"
            fi
        fi
    done
}

# Cleanup function
cleanup() {
    echo "Removing temporary files..."
    rm -rf "$TEMP_PROTO_DIR"
}

# Register cleanup on exit
trap cleanup EXIT

# Create necessary directories
mkdir -p "$TEMP_PROTO_DIR"
mkdir -p "$SCRIPT_DIR/results"
mkdir -p "$SCRIPT_DIR/ssl_creds"

CALLBACKS_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
PROTO_ROOT="$CALLBACKS_ROOT/../../python/protodef"

if [ -d "$PROTO_ROOT" ]; then
    SRC_PROTO_DIR="$PROTO_ROOT"
else
    echo "Error: Proto directory not found: $PROTO_ROOT"
    exit 1
fi

echo "Using proto directory: $SRC_PROTO_DIR"

# Copy essential protos
echo "Copying necessary proto files..."
copy_proto "envoy/service/ext_proc/v3/external_processor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/config/core/v3/socket_option.proto"
copy_proto "envoy/type/v3/range.proto"

# Run load tests for both scenarios
for scenario in "${TEST_SCENARIOS[@]}"; do
    echo -e "\nRunning load test for $scenario scenario..."
    
    # Select request data and token based on scenario
    if [ "$scenario" = "valid_jwt" ]; then
        request_data=$(printf "$REQUEST_DATA_VALID" "$VALID_TOKEN")
    else
        request_data=$(printf "$REQUEST_DATA_INVALID" "$INVALID_TOKEN")
    fi
    
    scenario_output="${OUTPUT_FILE%.*}_$scenario.json"
    
    ghz --insecure "$HOST:$PORT" \
      --proto "$PROTO_FILE" \
      --import-paths "$IMPORT_PATHS" \
      --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
      -d "$request_data" \
      -n "$TOTAL_REQUESTS" \
      -c "$CONCURRENT" \
      --timeout=5s \
      --connect-timeout=3s \
      -O json \
      -o "$scenario_output"
    
    test_result=$?
    
    # Process results
    if [ $test_result -eq 0 ] || [ -f "$scenario_output" ]; then
        echo "Results saved to $scenario_output"
        process_results "$scenario_output" "$scenario"
    else
        echo "Load test for $scenario failed."
    fi
done