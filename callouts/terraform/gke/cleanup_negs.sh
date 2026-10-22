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

# Script to detach and delete GKE-created NEGs before running terraform destroy

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
echo "GKE NEG Cleanup Script"
echo "========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Function to detach NEGs from a backend service
detach_negs() {
  local BACKEND_SERVICE=$1
  local NEG_NAME=$2

  echo "Checking backend service: $BACKEND_SERVICE for NEG: $NEG_NAME"

  # Get all zones in the region
  ZONES=$(gcloud compute zones list --filter="region:$REGION" --format="value(name)")

  for ZONE in $ZONES; do
    # Check if the NEG is attached to the backend service
    ATTACHED=$(gcloud compute backend-services describe $BACKEND_SERVICE \
      --region=$REGION \
      --project=$PROJECT_ID \
      --format="value(backends[].group)" 2>/dev/null | grep -c "$NEG_NAME" || true)

    if [ "$ATTACHED" -gt "0" ]; then
      echo "  → Detaching NEG $NEG_NAME in zone $ZONE from backend service $BACKEND_SERVICE"
      gcloud compute backend-services remove-backend $BACKEND_SERVICE \
        --network-endpoint-group=$NEG_NAME \
        --network-endpoint-group-zone=$ZONE \
        --region=$REGION \
        --project=$PROJECT_ID \
        --quiet
      echo "  ✓ Successfully detached"
    else
      echo "  ℹ NEG $NEG_NAME in zone $ZONE is not attached to $BACKEND_SERVICE"
    fi
  done
}

# Function to delete NEGs
delete_negs() {
  local NEG_NAME=$1
  echo "Looking for NEGs with name: $NEG_NAME to delete"

  # Get all zones in the region
  ZONES=$(gcloud compute zones list --filter="region:$REGION" --format="value(name)")

  for ZONE in $ZONES; do
    # Check if NEG exists in this zone
    if gcloud compute network-endpoint-groups list \
      --filter="name=$NEG_NAME AND zone:$ZONE" \
      --format="value(name)" \
      --project=$PROJECT_ID 2>/dev/null | grep -q "$NEG_NAME"; then

      echo "  → Deleting NEG $NEG_NAME in zone $ZONE"
      gcloud compute network-endpoint-groups delete $NEG_NAME \
        --zone=$ZONE \
        --project=$PROJECT_ID \
        --quiet
      echo "  ✓ Successfully deleted"
    fi
  done
}

echo "Step 1: Detaching NEGs from backend services..."
echo "=============================================="
detach_negs "callout-service-be" "callout-neg"
detach_negs "route-callout-service-be" "route-neg"
detach_negs "main-web-app-be" "main-app-neg"
detach_negs "secondary-app-be" "secondary-app-neg"
echo ""

echo "Step 2: Deleting the NEGs..."
echo "=============================================="
delete_negs "callout-neg"
delete_negs "route-neg"
delete_negs "main-app-neg"
delete_negs "secondary-app-neg"
echo ""

echo "========================================="
echo "NEG cleanup complete!"
echo "You can now safely run 'terraform destroy'."
echo "========================================="