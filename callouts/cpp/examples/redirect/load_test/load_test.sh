#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8080"  # Plaintext port
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# For redirect example, test request headers
REQUEST_DATA='{
  "request_headers": {
    "headers": {
      "headers": [
        {"key": "user-agent", "raw_value": "TW96aWxsYS81LjAgKGlQaG9uZTsgQ1BVIGlQaG9uZSBPUyAxNV8wIGxpa2UgTWFjIE9TIFgpIEFwcGxlV2ViS2l0LzYwNS4xLjE1IChLSFRNTCwgbGlrZSBHZWNrbykgVmVyc2lvbi8xNS4wIE1vYmlsZS8xNUUxNDggU2FmYXJpLzYwNC4x"}
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
    
    if [ -f "$result_file" ]; then
        echo "Summary:"
        if command -v jq &> /dev/null; then
            local count=$(jq '.count' "$result_file")
            local total=$(jq '.total' "$result_file")
            local average=$(jq '.average' "$result_file")
            local rps=$(jq '.rps' "$result_file")
            
            # Get redirect count from statusCodeDistribution
            local redirect_count=$(jq '.statusCodeDistribution.OK // 0' "$result_file")
            
            # Calculate success rate
            local success_rate="0.00"
            if [ "$count" != "0" ] && [ ! -z "$redirect_count" ]; then
                success_rate=$(echo "scale=2; $redirect_count * 100 / $count" | bc)
            fi
            
            local total_ms=$(echo "scale=2; $total / 1000000" | bc)
            local average_ms=$(echo "scale=2; $average / 1000000" | bc)
            
            printf "Total requests: %d\n" "$count"
            printf "Total time: %s ms\n" "$total_ms"
            printf "Average latency: %s ms\n" "$average_ms"
            printf "Requests per second: %s\n" "$rps"
            printf "Redirect success rate: %s%%\n" "$success_rate"
        else
            echo "Install jq for detailed summary: sudo apt install jq"
            echo "Raw results: $result_file"
        fi
    else
        echo "Test results not available"
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

# Calculate project root path
CALLBACKS_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
SRC_PROTO_DIR="$CALLBACKS_ROOT/../python/protodef"

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
copy_proto "envoy/type/v3/http_status.proto"

# Run load test
echo "Starting load test with $TOTAL_REQUESTS requests and $CONCURRENT concurrent connections"
ghz --insecure "$HOST:$PORT" \
  --proto "$PROTO_FILE" \
  --import-paths "$IMPORT_PATHS" \
  --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
  -d "$REQUEST_DATA" \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENT" \
  --timeout=5s \
  --connect-timeout=3s \
  -O json \
  -o "$OUTPUT_FILE"

test_result=$?

# Process results
if [ $test_result -eq 0 ] || [ -f "$OUTPUT_FILE" ]; then
    echo "Results saved to $OUTPUT_FILE"
    process_results "$OUTPUT_FILE"
else
    echo "Load test failed."
    exit 1
fi