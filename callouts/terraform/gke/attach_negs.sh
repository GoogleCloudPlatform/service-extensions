#!/bin/bash
# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Script to attach GKE-created NEGs to backend services
# This script should be run after Terraform deployment if NEGs are not automatically attached

set -e

# Check if required variables are provided
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <PROJECT_ID> <REGION>"
  echo "Example: $0 my-project us-central1"
  exit 1
fi

PROJECT_ID="$1"
REGION="$2"

echo "========================================="
echo "GKE NEG Attachment Script"
echo "========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Function to attach NEGs to a backend service
attach_negs() {
  local BACKEND_SERVICE=$1
  local NEG_NAME=$2

  echo "Looking for NEGs with name: $NEG_NAME"

  # Get all zones in the region
  ZONES=$(gcloud compute zones list --filter="region:$REGION" --format="value(name)")

  for ZONE in $ZONES; do
    # Check if NEG exists in this zone
    if gcloud compute network-endpoint-groups list \
      --filter="name=$NEG_NAME AND zone:$ZONE" \
      --format="value(name)" \
      --project=$PROJECT_ID 2>/dev/null | grep -q "$NEG_NAME"; then

      echo "✓ Found NEG $NEG_NAME in zone $ZONE"

      # Check if already attached
      ATTACHED=$(gcloud compute backend-services describe $BACKEND_SERVICE \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(backends[].group)" 2>/dev/null | grep -c "$NEG_NAME" || true)

      if [ "$ATTACHED" -eq "0" ]; then
        echo "  → Attaching NEG $NEG_NAME from zone $ZONE to backend service $BACKEND_SERVICE"
        gcloud compute backend-services add-backend $BACKEND_SERVICE \
          --network-endpoint-group=$NEG_NAME \
          --network-endpoint-group-zone=$ZONE \
          --balancing-mode=RATE \
          --max-rate-per-endpoint=100 \
          --region=$REGION \
          --project=$PROJECT_ID
        echo "  ✓ Successfully attached"
      else
        echo "  ℹ NEG $NEG_NAME already attached to $BACKEND_SERVICE"
      fi
    fi
  done
}

echo "Step 1: Checking for GKE-created NEGs..."
echo "========================================="
gcloud compute network-endpoint-groups list \
  --filter="name:(main-app-neg OR secondary-app-neg OR callout-neg OR route-neg)" \
  --project=$PROJECT_ID

echo ""
echo "Step 2: Attaching NEGs to backend services..."
echo "========================================="

# Attach NEGs for each service
attach_negs "callout-service-be" "callout-neg"
echo ""
attach_negs "route-callout-service-be" "route-neg"
echo ""
attach_negs "main-web-app-be" "main-app-neg"
echo ""
attach_negs "secondary-app-be" "secondary-app-neg"

echo ""
echo "========================================="
echo "Step 3: Verifying backend service health..."
echo "========================================="

for BACKEND in "main-web-app-be" "secondary-app-be" "callout-service-be" "route-callout-service-be"; do
  echo ""
  echo "Backend: $BACKEND"
  echo "─────────────────────────────────────"
  gcloud compute backend-services get-health $BACKEND \
    --region=$REGION \
    --project=$PROJECT_ID 2>/dev/null || echo "  ⚠ No health information available yet"
done

echo ""
echo "========================================="
echo "NEG attachment complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Wait 1-2 minutes for health checks to pass"
echo "2. Test your load balancer:"
echo "   LB_IP=\$(gcloud compute addresses describe main-app-lb-ip-gke --region=$REGION --project=$PROJECT_ID --format='value(address)')"
echo "   curl -k https://\$LB_IP/"
echo ""
