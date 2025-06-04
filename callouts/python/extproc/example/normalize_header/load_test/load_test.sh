#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8080"
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Device types to test: mobile, tablet, desktop
DEVICE_TYPES=("mobile" "tablet" "desktop")
REQUEST_DATA='{
  "request_headers": {
    "headers": {
      "headers": [
        {"key": ":authority", "raw_value": "DEVICE_HOST_PLACEHOLDER"}
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

# Run load tests for each device type
for device in "${DEVICE_TYPES[@]}"; do
    echo -e "\nRunning load test for $device devices..."
    
    # Set host value based on device type
    case $device in
        mobile) host_value="bS5leGFtcGxlLmNvbQ==" ;;  # m.example.com
        tablet) host_value="dC5leGFtcGxlLmNvbQ==" ;;  # t.example.com
        desktop) host_value="d3d3LmV4YW1wbGUuY29t" ;;  # www.example.com
    esac
    
    # Create device-specific request data
    device_data=$(echo "$REQUEST_DATA" | sed "s/DEVICE_HOST_PLACEHOLDER/$host_value/")
    device_output="${OUTPUT_FILE%.*}_$device.json"
    
    ghz --insecure "$HOST:$PORT" \
      --proto "$PROTO_FILE" \
      --import-paths "$IMPORT_PATHS" \
      --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
      -d "$device_data" \
      -n "$TOTAL_REQUESTS" \
      -c "$CONCURRENT" \
      -O json \
      -o "$device_output"
    
    # Process results
    if [ $? -eq 0 ]; then
        echo "Success! $device results saved to $device_output"
        if command -v jq &> /dev/null; then
            average=$(jq '.average' "$device_output")
            rps=$(jq '.rps' "$device_output")
            total_count=$(jq '.count' "$device_output")
            
            # Get success count from statusCodeDistribution
            ok_count=$(jq '.statusCodeDistribution.OK' "$device_output")
            
            # Calculate success percentage
            if [ "$total_count" != "0" ] && [ ! -z "$ok_count" ] && [ "$ok_count" != "0" ]; then
                success_rate=$(echo "scale=2; ($ok_count / $total_count) * 100" | bc)
            else
                success_rate="0.00"
            fi
            
            # Convert nanoseconds to milliseconds
            average_ms=$(echo "scale=2; $average / 1000000" | bc)
            
            printf "Device: %s | Avg latency: %sms | RPS: %s | Success: %s%%\n" \
                   "$device" "$average_ms" "$rps" "$success_rate"
        fi
    else
        echo "Load test for $device failed."
    fi
done