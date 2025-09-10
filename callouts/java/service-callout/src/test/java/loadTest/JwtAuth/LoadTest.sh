#!/bin/bash

# --- CONFIGURATION ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="localhost"
PORT="8181"
TOTAL_REQUESTS=${1:-1000}
CONCURRENT=${2:-50}

PROTO_DIR="$SCRIPT_DIR/temp_protos"
PROTO_IMPORTS="$PROTO_DIR/protodef"
PROTO_FILE="$PROTO_IMPORTS/envoy/service/ext_proc/v3/external_processor.proto"
RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$PROTO_IMPORTS" "$RESULTS_DIR"

VALID_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTcxMjE3MzQ2MSwiZXhwIjoyMDc1NjU4MjYxfQ.Vv-Lwn1z8BbVBGm-T1EKxv6T3XKCeRlvRrRmdu8USFdZUoSBK_aThzwzM2T8hlpReYsX9YFdJ3hMfq6OZTfHvfPLXvAt7iSKa03ZoPQzU8bRGzYy8xrb0ZQfrejGfHS5iHukzA8vtI2UAJ_9wFQiY5_VGHOBv9116efslbg-_gItJ2avJb0A0yr5uUwmE336rYEwgm4DzzfnTqPt8kcJwkONUsjEH__mePrva1qDT4qtfTPQpGa35TW8n9yZqse3h1w3xyxUfJd3BlDmoz6pQp2CvZkhdQpkWA1bnwpdqSDC7bHk4tYX6K5Q19na-2ff7gkmHZHJr0G9e_vAhQiE5w"
INVALID_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.invalid_signature"

# --- REQUEST PAYLOADS ---
REQUEST_TEMPLATE='{
  "request_headers": {
    "headers": {
      "headers": [
        {"key": "Authorization", "raw_value": "QmVhcmVyICVz"}
      ]
    },
    "end_of_stream": true
  }
}'

# --- FUNCTION: LOAD TEST RUNNER ---
run_test() {
  local scenario=$1
  local token=$2
  local request_data
  request_data=$(printf "$REQUEST_TEMPLATE" "$token")

  local output_file="$RESULTS_DIR/$(date +%Y%m%d_%H%M%S)_$scenario.json"

  echo "Running $scenario load test..."

  ghz --insecure "$HOST:$PORT" \
    --proto "$PROTO_FILE" \
    --import-paths "$PROTO_IMPORTS" \
    --call envoy.service.ext_proc.v3.ExternalProcessor/Process \
    -d "$request_data" \
    -n "$TOTAL_REQUESTS" \
    -c "$CONCURRENT" \
    -O json \
    -o "$output_file"

  if [ $? -eq 0 ]; then
    echo "✅ Test completed for $scenario."
    echo "🔍 Parsing metrics..."

    if command -v jq &>/dev/null; then
      avg=$(jq '.average' "$output_file")
      rps=$(jq '.rps' "$output_file")
      total=$(jq '.count' "$output_file")
      success=$(jq '.statusCodeDistribution.OK // 0' "$output_file")
      denied=$(jq '.statusCodeDistribution.PERMISSION_DENIED // 0' "$output_file")
      success_pct=$(echo "scale=2; $success * 100 / $total" | bc)

      echo "📊 Scenario: $scenario"
      echo "⏱️  Avg Latency: $(echo "$avg / 1000000" | bc) ms"
      echo "⚡ RPS: $rps"
      echo "✅ Success: $success_pct%"

      if [[ "$scenario" == "valid_jwt" ]]; then
        updated_headers=$(jq '[.details[] | select(.response.request_headers.response.header_mutation.set_headers != null)] | length' "$output_file")
        echo "🧩 Header mutations applied: $updated_headers"
      else
        rejections=$(jq '[.details[] | select(.error != null and contains("PERMISSION_DENIED"))] | length' "$output_file")
        echo "🚫 Requests denied (as expected): $rejections"
      fi
    fi
  else
    echo "❌ Test failed for $scenario."
  fi
}

# --- COPY PROTOS ---
copy_proto() {
  local src_root="$SCRIPT_DIR/../../../../protodef"
  local proto_file=$1
  local src="$src_root/$proto_file"
  local dst="$PROTO_IMPORTS/$proto_file"
  mkdir -p "$(dirname "$dst")"
  [ -f "$src" ] && cp "$src" "$dst"
}

echo "🔧 Copying proto files..."
copy_proto "envoy/service/ext_proc/v3/external_processsor.proto"
copy_proto "envoy/config/core/v3/address.proto"
copy_proto "envoy/type/v3/range.proto"

# --- EXECUTE TESTS ---
run_test "valid_jwt" "$VALID_TOKEN"
run_test "invalid_jwt" "$INVALID_TOKEN"
