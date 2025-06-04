#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8443"  # Porta padrão para SSL
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Request data com metadados
REQUEST_DATA_METADATA='[
  {
    "request_headers": {
      "headers": {
        "headers": [
          {"key": "example-header", "raw_value": "ZXhhbXBsZS12YWx1ZQ=="}
        ]
      },
      "end_of_stream": true
    },
    "metadata_context": {
      "filter_metadata": {
        "envoy.filters.http.ext_proc": {
          "fields": {
            "fr": {
              "string_value": "test-value"
            }
          }
        }
      }
    }
  }
]'

# Request data sem metadados
REQUEST_DATA_NO_METADATA='[
  {
    "request_headers": {
      "headers": {
        "headers": [
          {"key": "example-header", "raw_value": "ZXhhbXBsZS12YWx1ZQ=="}
        ]
      },
      "end_of_stream": true
    }
  }
]'

TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
OUTPUT_FILE_METADATA="$SCRIPT_DIR/results/metadata_$(date +%Y%m%d_%H%M%S).json"
OUTPUT_FILE_NO_METADATA="$SCRIPT_DIR/results/no_metadata_$(date +%Y%m%d_%H%M%S).json"

# Function to recursively copy protos
copy_proto() {
    local proto_file=$1
    local target_path="$TEMP_PROTO_DIR/protodef/$proto_file"
    local src_path="$SRC_PROTO_DIR/$proto_file"
    
    if [[ $proto_file == google/protobuf/* ]] && [ ! -f "$src_path" ]; then
        return 0
    fi
    
    if [ ! -f "$src_path" ]; then
        echo "Warning: File not found: $src_path (skipping)"
        return 0
    fi
    
    mkdir -p "$(dirname "$target_path")"
    cp "$src_path" "$target_path"
    
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

trap cleanup EXIT

mkdir -p "$TEMP_PROTO_DIR"
mkdir -p "$SCRIPT_DIR/results"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")")"
SRC_PROTO_DIR="$PROJECT_ROOT/protodef"

if [ ! -d "$SRC_PROTO_DIR" ]; then
    echo "Error: Proto directory not found: $SRC_PROTO_DIR"
    exit 1
fi

echo "Using proto directory: $SRC_PROTO_DIR"

echo "Copying necessary proto files..."
copy_proto "envoy/service/ext_proc/v3/external_processor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/config/core/v3/socket_option.proto"
copy_proto "envoy/type/v3/range.proto"

# Teste com metadados
echo "Starting METADATA test with $TOTAL_REQUESTS requests and $CONCURRENT concurrent connections"
ghz --insecure "$HOST:$PORT" \
  --proto "$PROTO_FILE" \
  --import-paths "$IMPORT_PATHS" \
  --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
  -d "$REQUEST_DATA_METADATA" \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENT" \
  -O json \
  -o "$OUTPUT_FILE_METADATA"

# Teste sem metadados
echo "Starting NO METADATA test with $TOTAL_REQUESTS requests and $CONCURRENT concurrent connections"
ghz --insecure "$HOST:$PORT" \
  --proto "$PROTO_FILE" \
  --import-paths "$IMPORT_PATHS" \
  --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
  -d "$REQUEST_DATA_NO_METADATA" \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENT" \
  -O json \
  -o "$OUTPUT_FILE_NO_METADATA"

# Process results
process_results() {
    local file=$1
    local name=$2
    
    if [ -f "$file" ]; then
        echo "Summary for $name test:"
        if command -v jq &> /dev/null; then
            count=$(jq '.count' "$file")
            total=$(jq '.total' "$file")
            average=$(jq '.average' "$file")
            rps=$(jq '.rps' "$file")
            
            # Get success count from statusCodeDistribution
            ok_count=$(jq '.statusCodeDistribution.OK' "$file")
            
            # Calculate success percentage
            if [ "$count" != "0" ] && [ ! -z "$ok_count" ] && [ "$ok_count" != "0" ]; then
                success_rate=$(echo "scale=2; ($ok_count / $count) * 100" | bc)
            else
                success_rate="0.00"
            fi
            
            total_ms=$(echo "scale=2; $total / 1000000" | bc)
            average_ms=$(echo "scale=2; $average / 1000000" | bc)
            
            printf "Total requests: %d\n" "$count"
            printf "Total time: %s ms\n" "$total_ms"
            printf "Average latency: %s ms\n" "$average_ms"
            printf "Requests per second: %s\n" "$rps"
            printf "Success rate: %s%%\n" "$success_rate"
            
            # Report whether metadata was processed correctly
            if [ "$name" = "METADATA" ]; then
                echo "Metadata processing: $ok_count requests successfully processed metadata"
            else
                echo "No metadata: $ok_count requests successfully processed without metadata"
            fi
        else
            echo "Install jq for detailed summary: sudo apt install jq"
            echo "Raw results: $file"
        fi
    else
        echo "Results for $name test not available"
    fi
}

process_results "$OUTPUT_FILE_METADATA" "METADATA"
process_results "$OUTPUT_FILE_NO_METADATA" "NO METADATA"

echo "Results saved to:"
[ -f "$OUTPUT_FILE_METADATA" ] && echo "- Metadata cases: $OUTPUT_FILE_METADATA"
[ -f "$OUTPUT_FILE_NO_METADATA" ] && echo "- No metadata cases: $OUTPUT_FILE_NO_METADATA"

# Compare results if both tests completed successfully
if [ -f "$OUTPUT_FILE_METADATA" ] && [ -f "$OUTPUT_FILE_NO_METADATA" ]; then
    echo -e "\nPerformance Comparison:"
    
    if command -v jq &> /dev/null; then
        meta_avg=$(jq '.average' "$OUTPUT_FILE_METADATA")
        no_meta_avg=$(jq '.average' "$OUTPUT_FILE_NO_METADATA")
        meta_avg_ms=$(echo "scale=2; $meta_avg / 1000000" | bc)
        no_meta_avg_ms=$(echo "scale=2; $no_meta_avg / 1000000" | bc)
        
        meta_rps=$(jq '.rps' "$OUTPUT_FILE_METADATA")
        no_meta_rps=$(jq '.rps' "$OUTPUT_FILE_NO_METADATA")
        
        diff_pct=$(echo "scale=2; (($meta_avg - $no_meta_avg) / $no_meta_avg) * 100" | bc)
        
        echo "With metadata: $meta_avg_ms ms latency, $meta_rps RPS"
        echo "Without metadata: $no_meta_avg_ms ms latency, $no_meta_rps RPS"
        echo "Overhead of using metadata: $diff_pct% in latency"
    fi
fi