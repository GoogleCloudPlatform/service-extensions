#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8080"
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Request data for successful call (with required headers)
REQUEST_DATA_SUCCESS='[
  {
    "request_headers": {
      "headers": {
        "headers": [
          {"key": "header-check", "raw_value": "c29tZS12YWx1ZQ=="}
        ]
      },
      "end_of_stream": true
    }
  },
  {
    "request_body": {
      "body": "Ym9keS1jaGVjaw==",
      "end_of_stream": true
    }
  }
]'

# Request data for failed call (missing required headers)
REQUEST_DATA_FAIL='[
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
OUTPUT_FILE_SUCCESS="$SCRIPT_DIR/results/success_$(date +%Y%m%d_%H%M%S).json"
OUTPUT_FILE_FAIL="$SCRIPT_DIR/results/fail_$(date +%Y%m%d_%H%M%S).json"

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
        echo "Summary for ${test_type} test:"
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
        echo "${test_type} test results not available"
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

# Run load test for successful requests
echo "Starting SUCCESS load test with $TOTAL_REQUESTS requests and $CONCURRENT concurrent connections"
ghz --insecure "$HOST:$PORT" \
  --proto "$PROTO_FILE" \
  --import-paths "$IMPORT_PATHS" \
  --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
  -d "$REQUEST_DATA_SUCCESS" \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENT" \
  -O json \
  -o "$OUTPUT_FILE_SUCCESS"

success_test_result=$?

# Run load test for failed requests
echo "Starting FAIL load test with $TOTAL_REQUESTS requests and $CONCURRENT concurrent connections"
ghz --insecure "$HOST:$PORT" \
  --proto "$PROTO_FILE" \
  --import-paths "$IMPORT_PATHS" \
  --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
  -d "$REQUEST_DATA_FAIL" \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENT" \
  -O json \
  -o "$OUTPUT_FILE_FAIL"

fail_test_result=$?

# Process results
echo -e "\nProcessing results..."
if [ $success_test_result -eq 0 ] || [ -f "$OUTPUT_FILE_SUCCESS" ]; then
    process_results "$OUTPUT_FILE_SUCCESS" "SUCCESS"
else
    echo "SUCCESS test failed to run properly."
fi

if [ $fail_test_result -eq 0 ] || [ -f "$OUTPUT_FILE_FAIL" ]; then
    process_results "$OUTPUT_FILE_FAIL" "FAIL"
else
    echo "FAIL test failed to run properly."
fi

echo -e "\nResults saved to:"
[ -f "$OUTPUT_FILE_SUCCESS" ] && echo "- Success cases: $OUTPUT_FILE_SUCCESS"
[ -f "$OUTPUT_FILE_FAIL" ] && echo "- Fail cases: $OUTPUT_FILE_FAIL"

# Compare results if both tests completed successfully
if [ -f "$OUTPUT_FILE_SUCCESS" ] && [ -f "$OUTPUT_FILE_FAIL" ]; then
    echo -e "\nPerformance Comparison:"
    
    if command -v jq &> /dev/null; then
        success_avg=$(jq '.average' "$OUTPUT_FILE_SUCCESS")
        fail_avg=$(jq '.average' "$OUTPUT_FILE_FAIL")
        success_avg_ms=$(echo "scale=2; $success_avg / 1000000" | bc)
        fail_avg_ms=$(echo "scale=2; $fail_avg / 1000000" | bc)
        
        success_rps=$(jq '.rps' "$OUTPUT_FILE_SUCCESS")
        fail_rps=$(jq '.rps' "$OUTPUT_FILE_FAIL")
        
        # Calculate success rates
        success_count=$(jq '.count' "$OUTPUT_FILE_SUCCESS")
        fail_count=$(jq '.count' "$OUTPUT_FILE_FAIL")
        success_ok=$(jq '.statusCodeDistribution.OK' "$OUTPUT_FILE_SUCCESS")
        fail_ok=$(jq '.statusCodeDistribution.OK' "$OUTPUT_FILE_FAIL")
        
        success_rate="0.00"
        fail_rate="0.00"
        
        if [ ! -z "$success_ok" ] && [ "$success_ok" != "null" ]; then
            success_rate=$(echo "scale=2; ($success_ok / $success_count) * 100" | bc)
        fi
        
        if [ ! -z "$fail_ok" ] && [ "$fail_ok" != "null" ]; then
            fail_rate=$(echo "scale=2; ($fail_ok / $fail_count) * 100" | bc)
        fi
        
        # Calculate performance difference
        if [ "$fail_avg" != "0" ] && [ "$fail_avg" != "null" ]; then
            diff_pct=$(echo "scale=2; (($success_avg - $fail_avg) / $fail_avg) * 100" | bc)
            
            echo "Success cases: $success_avg_ms ms latency, $success_rps RPS, $success_rate% success rate"
            echo "Fail cases: $fail_avg_ms ms latency, $fail_rps RPS, $fail_rate% success rate"
            
            if (( $(echo "$diff_pct > 0" | bc -l) )); then
                echo "Success cases are slower by $diff_pct% compared to fail cases"
            else
                pos_diff=$(echo "scale=2; $diff_pct * -1" | bc)
                echo "Success cases are faster by $pos_diff% compared to fail cases"
            fi
        fi
    else
        echo "Install jq for detailed comparison: sudo apt install jq"
    fi
fi