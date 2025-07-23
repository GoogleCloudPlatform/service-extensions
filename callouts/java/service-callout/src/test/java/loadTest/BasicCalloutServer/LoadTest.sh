#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8443"  # Change if your server listens on a different port
PROTO_FILE="$SCRIPT_DIR/proto/envoy/service/ext_proc/v3/external_processor.proto"
IMPORT_PATHS="$SCRIPT_DIR/proto"

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
      "body": "b3JpZ2luYWwtYm9keQ==",  // "original-body"
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
      "body": "b3JpZ2luYWwtYm9keQ==",  // "original-body"
      "end_of_stream": true
    }
  }
]'

TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-20}
OUTPUT_DIR="$SCRIPT_DIR/results"
mkdir -p "$OUTPUT_DIR"
OUTPUT_FILE="$OUTPUT_DIR/results_$(date +%Y%m%d_%H%M%S).json"

# Run GHZ
echo "Running GHZ load test..."
ghz \
  --insecure \
  --proto "$PROTO_FILE" \
  --import-paths "$IMPORT_PATHS" \
  --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
  -d "$REQUEST_DATA" \
  -n "$TOTAL_REQUESTS" \
  -c "$CONCURRENT" \
  --timeout=5s \
  --connect-timeout=2s \
  -O json \
  -o "$OUTPUT_FILE"

# Summary
echo "Test complete. Summary:"
if command -v jq &>/dev/null; then
    jq '. | {
      requests: .count,
      average_ms: (.average / 1000000),
      rps: .rps,
      success: .statusCodeDistribution.OK,
      total_time_ms: (.total / 1000000)
    }' "$OUTPUT_FILE"
else
    echo "Install jq to view summary. Raw results saved to: $OUTPUT_FILE"
fi
