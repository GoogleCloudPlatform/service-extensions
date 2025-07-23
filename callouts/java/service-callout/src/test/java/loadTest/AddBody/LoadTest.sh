#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8181"  # Adjust if needed

# Paths
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Example request simulating a request body (triggers `onRequestBody`)
REQUEST_DATA='{
  "request_body": {
    "body": "aGVsbG8gd29ybGQ=",  # "hello world" base64
    "end_of_stream": true
  }
}'

# Load test params
TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
OUTPUT_FILE="$SCRIPT_DIR/results/$(date +%Y%m%d_%H%M%S).json"

# Cleanup
cleanup() {
    rm -rf "$TEMP_PROTO_DIR"
}
trap cleanup EXIT

# Copy Protos
copy_proto() {
    local proto_file=$1
    local src="$SRC_PROTO_DIR/$proto_file"
    local dst="$TEMP_PROTO_DIR/protodef/$proto_file"

    [[ ! -f "$src" ]] && echo "Warning: $src not found, skipping." && return

    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"

    grep '^import ' "$src" | sed -E 's/import "(.*)";/\1/' | while read -r import_file; do
        copy_proto "$import_file"
    done
}

# Proto source root
CALLBACKS_ROOT="$(dirname "$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")")"
PROTO_ROOT="$CALLBACKS_ROOT/../../python/protodef"
[[ ! -d "$PROTO_ROOT" ]] && echo "ERROR: Proto root not found at $PROTO_ROOT" && exit 1
SRC_PROTO_DIR="$PROTO_ROOT"

mkdir -p "$TEMP_PROTO_DIR/protodef" "$SCRIPT_DIR/results"

# Required protos
copy_proto "envoy/service/ext_proc/v3/external_processor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/config/core/v3/socket_option.proto"
copy_proto "envoy/type/v3/range.proto"

# Run GHZ
echo "Running GHZ load test..."
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

# Display summary
if [ -f "$OUTPUT_FILE" ]; then
    echo "Test complete. Results saved to $OUTPUT_FILE"
    if command -v jq &>/dev/null; then
        jq '{
            total_requests: .count,
            total_time_ms: (.total / 1000000 | floor),
            avg_latency_ms: (.average / 1000000 | floor),
            rps: .rps,
            success_rate_percent: (.statusCodeDistribution.OK // 0 / .count * 100)
        }' "$OUTPUT_FILE"
    else
        echo "Install 'jq' for pretty results."
    fi
else
    echo "GHZ test failed!"
    exit 1
fi
