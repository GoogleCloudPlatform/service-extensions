#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8181"
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# JSON payload to trigger redirect
REQUEST_DATA='{
  "request_headers": {
    "headers": {
      "headers": [
        {"key": "user-agent", "raw_value": "test-agent"}
      ]
    },
    "end_of_stream": true
  }
}'

TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
RESULTS_DIR="$SCRIPT_DIR/results"
OUTPUT_FILE="$RESULTS_DIR/ghz_redirect_$(date +%Y%m%d_%H%M%S).json"

# Proto source directory
PROTO_SRC_DIR="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Function to recursively copy proto dependencies
copy_proto() {
  local proto_file=$1
  local src_path="$PROTO_SRC_DIR/$proto_file"
  local dest_path="$IMPORT_PATHS/$proto_file"

  [ ! -f "$src_path" ] && echo "Missing proto: $src_path" && return

  mkdir -p "$(dirname "$dest_path")"
  cp "$src_path" "$dest_path"

  grep '^import ' "$src_path" | sed 's/^import "\(.*\)";/\1/' | while read -r import_file; do
    copy_proto "$import_file"
  done
}

# Cleanup
trap "rm -rf $TEMP_PROTO_DIR" EXIT
mkdir -p "$IMPORT_PATHS" "$RESULTS_DIR"

echo "Copying protos..."
copy_proto "envoy/service/ext_proc/v3/external_processor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/config/core/v3/socket_option.proto"
copy_proto "envoy/type/v3/range.proto"
copy_proto "envoy/type/v3/http_status.proto"

# Run ghz
echo "Running ghz load test..."
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

# Output result summary
echo "Test results saved at: $OUTPUT_FILE"
if command -v jq &> /dev/null; then
  jq '{total_requests: .count, total_time_ns: .total, avg_latency_ns: .average, rps: .rps, success_distribution: .statusCodeDistribution}' "$OUTPUT_FILE"
else
  echo "Install jq to parse output: sudo apt install jq"
fi
