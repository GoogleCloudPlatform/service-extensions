#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8080"
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Request data for valid IP selection (without comments)
REQUEST_DATA_VALID='[
  {
    "request_headers": {
      "headers": {
        "headers": [
          {"key": "ip-to-return", "raw_value": "MTAuMS4xMC4y"}
        ]
      },
      "end_of_stream": true
    }
  }
]'

# Request data for default IP selection
REQUEST_DATA_DEFAULT='[
  {
    "request_headers": {
      "headers": {
        "headers": [
          {"key": "other-header", "raw_value": "c29tZS12YWx1ZQ=="}
        ]
      },
      "end_of_stream": true
    }
  }
]'

TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
OUTPUT_FILE_VALID="$SCRIPT_DIR/results/valid_$(date +%Y%m%d_%H%M%S).json"
OUTPUT_FILE_DEFAULT="$SCRIPT_DIR/results/default_$(date +%Y%m%d_%H%M%S).json"

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
            # Skip if source doesn't exist
            if [ -f "$SRC_PROTO_DIR/$import_file" ]; then
                cp "$SRC_PROTO_DIR/$import_file" "$import_target"
                copy_proto "$import_file"
            fi
        fi
    done
}

# Function to process test results
process_results() {
    local result_file=$1
    local test_type=$2
    
    if [ -f "$result_file" ]; then
        echo "Summary for ${test_type} IP test:"
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
            printf "Total time: %s ms\n" "$total_ms"
            printf "Average latency: %s ms\n" "$average_ms"
            printf "Requests per second: %s\n" "$rps"
            printf "Success rate: %s%%\n" "$success_rate"
        else
            echo "Install jq for detailed summary: sudo apt install jq"
            echo "Raw results: $result_file"
        fi
    else
        echo "${test_type} IP test results not available"
    fi
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

# Run load test for valid IP selection
echo "Starting VALID IP load test with $TOTAL_REQUESTS requests and $CONCURRENT concurrent connections"
ghz --insecure "$HOST:$PORT" \
  --proto "$PROTO_FILE" \
  --import-paths "$IMPORT_PATHS" \
  --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
  -d "$REQUEST_DATA_VALID" \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENT" \
  -O json \
  -o "$OUTPUT_FILE_VALID"

valid_result=$?

# Run load test for default IP selection only if the first test succeeded
if [ $valid_result -eq 0 ]; then
  echo "Starting DEFAULT IP load test with $TOTAL_REQUESTS requests and $CONCURRENT concurrent connections"
  ghz --insecure "$HOST:$PORT" \
    --proto "$PROTO_FILE" \
    --import-paths "$IMPORT_PATHS" \
    --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
    -d "$REQUEST_DATA_DEFAULT" \
    -n "$TOTAL_REQUESTS" \
    -c "$CONCURRENT" \
    -O json \
    -o "$OUTPUT_FILE_DEFAULT"
else
  echo "VALID IP load test failed, skipping DEFAULT IP test"
fi

# Process results
echo -e "\nProcessing results..."
process_results "$OUTPUT_FILE_VALID" "VALID"
process_results "$OUTPUT_FILE_DEFAULT" "DEFAULT"

echo -e "\nResults saved to:"
[ -f "$OUTPUT_FILE_VALID" ] && echo "- Valid IP cases: $OUTPUT_FILE_VALID"
[ -f "$OUTPUT_FILE_DEFAULT" ] && echo "- Default IP cases: $OUTPUT_FILE_DEFAULT"

# Compare results if both tests completed successfully
if [ -f "$OUTPUT_FILE_VALID" ] && [ -f "$OUTPUT_FILE_DEFAULT" ]; then
    echo -e "\nPerformance Comparison:"
    
    if command -v jq &> /dev/null; then
        valid_avg=$(jq '.average' "$OUTPUT_FILE_VALID")
        default_avg=$(jq '.average' "$OUTPUT_FILE_DEFAULT")
        valid_avg_ms=$(echo "scale=2; $valid_avg / 1000000" | bc)
        default_avg_ms=$(echo "scale=2; $default_avg / 1000000" | bc)
        
        valid_rps=$(jq '.rps' "$OUTPUT_FILE_VALID")
        default_rps=$(jq '.rps' "$OUTPUT_FILE_DEFAULT")
        
        # Calculate success rates
        valid_count=$(jq '.count' "$OUTPUT_FILE_VALID")
        default_count=$(jq '.count' "$OUTPUT_FILE_DEFAULT")
        valid_ok=$(jq '.statusCodeDistribution.OK' "$OUTPUT_FILE_VALID")
        default_ok=$(jq '.statusCodeDistribution.OK' "$OUTPUT_FILE_DEFAULT")
        
        valid_success="0.00"
        default_success="0.00"
        
        if [ ! -z "$valid_ok" ] && [ "$valid_ok" != "null" ]; then
            valid_success=$(echo "scale=2; ($valid_ok / $valid_count) * 100" | bc)
        fi
        
        if [ ! -z "$default_ok" ] && [ "$default_ok" != "null" ]; then
            default_success=$(echo "scale=2; ($default_ok / $default_count) * 100" | bc)
        fi
        
        # Calculate performance difference
        if [ "$default_avg" != "0" ] && [ "$default_avg" != "null" ]; then
            diff_pct=$(echo "scale=2; (($valid_avg - $default_avg) / $default_avg) * 100" | bc)
            
            echo "Valid IP selection: $valid_avg_ms ms latency, $valid_rps RPS, $valid_success% success rate"
            echo "Default IP selection: $default_avg_ms ms latency, $default_rps RPS, $default_success% success rate"
            
            if (( $(echo "$diff_pct > 0" | bc -l) )); then
                echo "Using specific IP is slower by $diff_pct% compared to default IP"
            else
                pos_diff=$(echo "scale=2; $diff_pct * -1" | bc)
                echo "Using specific IP is faster by $pos_diff% compared to default IP"
            fi
        fi
    else
        echo "Install jq for detailed comparison: sudo apt install jq"
    fi
fi