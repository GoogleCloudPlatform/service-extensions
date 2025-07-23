#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8443"  # Change to match your AddHeader server port
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# Sample headers to test onRequestHeaders and onResponseHeaders behavior
REQUEST_DATA='[
  {
    "request_headers": {
      "headers": {
        "headers": [
          {"key": "user-agent", "raw_value": "Z2hwLXRlc3Q="}
        ]
      },
      "end_of_stream": true
    }
  },
  {
    "response_headers": {
      "headers": {
        "headers": [
          {"key": "foo", "raw_value": "YmFy"}  # Should be removed by AddHeader
        ]
      },
      "end_of_stream": true
    }
  }
]'

TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
RESULTS_DIR="$SCRIPT_DIR/results"
OUTPUT_FILE="$RESULTS_DIR/$(date +%Y%m%d_%H%M%S)_add_header.json"

mkdir -p "$RESULTS_DIR" "$TEMP_PROTO_DIR"

# Proto copying helper
copy_proto() {
    local proto=$1
    local src="$PROTO_SRC_ROOT/$proto"
    local dst="$IMPORT_PATHS/$proto"

    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        grep '^import ' "$src" | sed -n 's/import "\(.*\)";/\1/p' | while read -r dep; do
            copy_proto "$dep"
        done
    else
        echo "Warning: Missing proto: $src"
    fi
}

# Detect proto source root (adjust this if your structure differs)
CALLBACKS_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
PROTO_SRC_ROOT="$CALLBACKS_ROOT/python/protodef"
if [ ! -d "$PROTO_SRC_ROOT" ]; then
    echo "Error: Could not locate proto source at $PROTO_SRC_ROOT"
    exit 1
fi

# Copy required protos
echo "Copying protos..."
copy_proto "envoy/service/ext_proc/v3/external_processor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/config/core/v3/socket_option.proto"
copy_proto "envoy/type/v3/range.proto"

# Run the GHZ load test
echo "Running load test..."
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

# Process results
echo "Load test complete: $OUTPUT_FILE"
if command -v jq &> /dev/null; then
    jq -r '
      "Total Requests: \(.count)",
      "Total Time (ms): \(.total / 1000000)",
      "Average Latency (ms): \(.average / 1000000)",
      "RPS: \(.rps)",
      "Success Rate: \(.statusCodeDistribution.OK // 0 * 100 / .count)%"
    ' "$OUTPUT_FILE"
else
    echo "Install jq to parse test results."
    echo "Raw output: $OUTPUT_FILE"
fi

# Cleanup protos
rm -rf "$TEMP_PROTO_DIR"
