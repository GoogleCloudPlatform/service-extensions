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

# Copy SSL credentials
echo "Copying SSL credentials..."
cp "$SCRIPT_DIR/../../../../ssl_creds/publickey.pem" "$SCRIPT_DIR/ssl_creds/"
cp "$SCRIPT_DIR/../../../../ssl_creds/privatekey.pem" "$SCRIPT_DIR/ssl_creds/"

# Absolute path to original protos
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")")"
SRC_PROTO_DIR="$PROJECT_ROOT/protodef"

# Verify proto directory exists
if [ ! -d "$SRC_PROTO_DIR" ]; then
    echo "Error: Proto directory not found: $SRC_PROTO_DIR"
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
      -O json \
      -o "$scenario_output"
    
    # Process results
    if [ $? -eq 0 ]; then
        echo "Success! $scenario results saved to $scenario_output"
        if command -v jq &> /dev/null; then
            average=$(jq '.average' "$scenario_output")
            rps=$(jq '.rps' "$scenario_output")
            total_count=$(jq '.count' "$scenario_output")
            
            # Get success/failure counts
            ok_count=$(jq '.statusCodeDistribution.OK // 0' "$scenario_output")
            denied_count=$(jq '.statusCodeDistribution.PERMISSION_DENIED // 0' "$scenario_output")
            
            # Calculate success percentage
            if [ "$scenario" = "valid_jwt" ]; then
                success_rate=$(echo "scale=2; $ok_count * 100 / $total_count" | bc)
            else
                success_rate=$(echo "scale=2; $denied_count * 100 / $total_count" | bc)
            fi
            
            # Convert nanoseconds to milliseconds
            average_ms=$(echo "scale=2; $average / 1000000" | bc)
            
            printf "Scenario: %s | Avg latency: %sms | RPS: %s | Expected result rate: %s%%\n" \
                   "$scenario" "$average_ms" "$rps" "$success_rate"
            
            # Verify behavior
            if [ "$scenario" = "valid_jwt" ]; then
                header_updates=$(jq '[.details[] | select(.response.request_headers.response.header_mutation.set_headers != null)] | length' "$scenario_output")
                echo "Valid JWT - Header mutations applied: $header_updates"
            else
                denials=$(jq '[.details[] | select(.error != null and contains("PERMISSION_DENIED"))] | length' "$scenario_output")
                echo "Invalid JWT - Requests denied: $denials"
            fi
        fi
    else
        echo "Load test for $scenario failed."
    fi
done