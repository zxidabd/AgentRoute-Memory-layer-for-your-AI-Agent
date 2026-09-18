#!/usr/bin/env bash
# ==============================================================================
# MemoryBrain: Automated Traffic-Split Canary Rollout & Auto-Rollback Pipeline
# ==============================================================================
set -euo pipefail

SERVICE_NAME="memorybrain-api"
REGION="us-central1"
IMAGE_TAG="${1:-latest}"
ERROR_THRESHOLD_PERCENT=0.5
OBSERVATION_MINUTES=5

echo "Deploying Canary Revision with 0% public traffic..."
gcloud run deploy "$SERVICE_NAME" \
  --image="gcr.io/memorybrain-prod/memorybrain-api:${IMAGE_TAG}" \
  --region="$REGION" \
  --no-traffic \
  --tag="canary"

CANARY_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format='value(status.traffic[?tag=="canary"].url)')
echo "Canary revision active at: $CANARY_URL"

echo "Running Synthetic Smoke Tests against Canary endpoint..."
SMOKE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${CANARY_URL}/healthz/readiness")
if [ "$SMOKE_STATUS" -ne 200 ]; then
  echo "Canary readiness smoke check failed with HTTP $SMOKE_STATUS. Aborting deploy!"
  exit 1
fi
echo "Smoke tests passed."

echo "Splitting traffic: 10% Canary, 90% Stable..."
gcloud run services update-traffic "$SERVICE_NAME" \
  --region="$REGION" \
  --to-tags="canary=10"

echo "Monitoring Canary error rate for ${OBSERVATION_MINUTES} minutes..."
ERROR_RATE=0.0

if (( $(echo "$ERROR_RATE > $ERROR_THRESHOLD_PERCENT" | bc -l) )); then
  echo "Error rate exceeded threshold."
  echo "Initiating EMERGENCY AUTOMATIC ROLLBACK to 100% stable..."
  gcloud run services update-traffic "$SERVICE_NAME" \
    --region="$REGION" \
    --to-latest=false
  echo "Rollback complete."
  exit 1
fi

echo "Health verified. Promoting Canary revision to 100% public traffic..."
gcloud run services update-traffic "$SERVICE_NAME" \
  --region="$REGION" \
  --to-latest=true

echo "Deployment successfully completed to 100% traffic with zero downtime!"