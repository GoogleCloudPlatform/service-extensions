#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8181"
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Request with JSON body
REQUEST_DATA='{
  "request_headers": {},
  "request_body": {
    "body": "ewogICJtZXNzYWdlIjogIkhlbGxvIFdvcmxkIiwKICAic3RhdHVzIjogIm9rIgp9",
    "end_of_stream": true
  }
}'

TOTAL_REQUESTS=${1:-800}   # Lower due to buffering
CONCURRENT=${2:-10}         # Lower concurrency
OUTPUT_FILE="$SCRIPT_DIR/results/$(date +%Y%m%d_%H%M%S).json"

# Function to process results (same as other scripts)
process_results() {
    local result_file=$1

    if [ -f "$result_file" ]; then
        echo "Summary:"
        if command -v jq &> /dev/null; then
            local count=$(jq '.count' "$result_file")
            local total=$(jq '.total' "$result_file")
            local average=$(jq '.average' "$result_file")
            local rps=$(jq '.rps' "$result_file")

            # Get success count from statusCodeDistribution
            local ok_count=$(jq '.statusCodeDistribution.OK' "$result_file")

            # Calculate success rate
            local success_rate="0.00"
            if [ "$count" != "0" ] && [ ! -z "$ok_count" ] && [ "$ok_count" != "null" ]; then
                success_rate=$(echo "scale=2; ($ok_count / $count) * 100" | bc)
            fi

            local total_ms=$(echo "scale=2; $total / 1000000" | bc)
            local average_ms=$(echo "scale=2; $average / 1000000" | bc)

            printf "Total requests: %d\n" "$count"
            printf "Total time: %.2f ms\n" "$total_ms"
            printf "Average latency: %.2f ms\n" "$average_ms"
            printf "Requests per second: %.2f\n" "$rps"
            printf "Success rate: %.2f%%\n" "$success_rate"
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
    rm -rf "$TEMP_PROTO_DIR"
}
trap cleanup EXIT

mkdir -p "$TEMP_PROTO_DIR" "$SCRIPT_DIR/results"

CALLBACKS_ROOT="$(dirname "$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
PROTO_ROOT="$CALLBACKS_ROOT/../../python/protodef"

if [ -d "$PROTO_ROOT" ]; then
    SRC_PROTO_DIR="$PROTO_ROOT"
else
    echo "Error: Proto directory not found: $PROTO_ROOT"
    exit 1
fi

echo "Copying necessary proto files..."
copy_proto "envoy/service/ext_proc/v3/external_processor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/config/core/v3/socket_option.proto"
copy_proto "envoy/type/v3/range.proto"

echo "Starting load test..."
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

if [ -f "$OUTPUT_FILE" ]; then
    process_results "$OUTPUT_FILE"
else
    echo "Load test failed!"
    exit 1
fi