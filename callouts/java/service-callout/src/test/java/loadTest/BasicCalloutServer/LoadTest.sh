#!/bin/bash

# === Config ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8443"  # Match the Java server's default port
TEMP_PROTO_DIR="$SCRIPT_DIR/temp_protos"
IMPORT_PATHS="$TEMP_PROTO_DIR/protodef"
PROTO_FILE="$IMPORT_PATHS/envoy/service/ext_proc/v3/external_processor.proto"

# === JSON test payload ===
REQUEST_DATA='[
  {
    "request_headers": {
      "headers": {
        "headers": [
          {"key": "example-header", "raw_value": "ZXhhbXBsZS12YWx1ZQ=="}
        ]
      },
      "end_of_stream": true
    }
  },
  {
    "request_body": {
      "body": "b3JpZ2luYWwtYm9keQ==",
      "end_of_stream": true
    }
  },
  {
    "response_headers": {
      "headers": {
        "headers": [
          {"key": "response-header", "raw_value": "cmVzcG9uc2UtdmFsdWU="}
        ]
      },
      "end_of_stream": true
    }
  },
  {
    "response_body": {
      "body": "b3JpZ2luYWwtYm9keQ==",
      "end_of_stream": true
    }
  }
]'

# === Load test parameters ===
TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
OUTPUT_FILE="$SCRIPT_DIR/results/$(date +%Y%m%d_%H%M%S).json"

# === Proto Copy Function ===
copy_proto() {
    local proto_file=$1
    local src_path="$SRC_PROTO_DIR/$proto_file"
    local dest_path="$IMPORT_PATHS/$proto_file"

    [ ! -f "$src_path" ] && echo "Missing proto: $proto_file" && return

    mkdir -p "$(dirname "$dest_path")"
    cp "$src_path" "$dest_path"

    # Recursively copy dependencies
    grep '^import ' "$src_path" | sed -e 's/import "//' -e 's/";//' | while read dep; do
        [ ! -f "$IMPORT_PATHS/$dep" ] && copy_proto "$dep"
    done
}

# === Setup ===
cleanup() { rm -rf "$TEMP_PROTO_DIR"; }
trap cleanup EXIT

mkdir -p "$IMPORT_PATHS" "$SCRIPT_DIR/results"

# Adjust this to the actual proto source root directory on your system
SRC_PROTO_DIR="/ABSOLUTE/PATH/TO/envoy/proto/root"
echo "Copying protos from $SRC_PROTO_DIR"

copy_proto "envoy/service/ext_proc/v3/external_processor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/config/core/v3/socket_option.proto"
copy_proto "envoy/type/v3/range.proto"

# === Run GHZ ===
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

# === Results ===
if [ -f "$OUTPUT_FILE" ]; then
  echo "Results saved to $OUTPUT_FILE"
else
  echo "Load test failed!"
  exit 1
fi
