#!/usr/bin/env bash
# One-time: create alcohol-label-checker-dev (same env + ACR as production).
# Run after production Container App exists (copies registry settings pattern).
#
# Usage: ./scripts/azure-create-dev-container-app.sh

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-alcohol-label-checker}"
PROD_APP="${PROD_APP:-alcohol-label-checker}"
DEV_APP="${DEV_APP:-alcohol-label-checker-dev}"
ACR_NAME="${ACR_NAME:-ca2810cf1acbacr}"
PROD_IMAGE_REPO="${PROD_IMAGE_REPO:-alcohol-label-checker}"

if az containerapp show -n "$DEV_APP" -g "$RESOURCE_GROUP" &>/dev/null; then
  STATE="$(az containerapp show -n "$DEV_APP" -g "$RESOURCE_GROUP" --query properties.provisioningState -o tsv)"
  FQDN="$(az containerapp show -n "$DEV_APP" -g "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)"
  if [ "$STATE" = "Succeeded" ] && [ -n "$FQDN" ] && [ "$FQDN" != "null" ]; then
    echo "Container app ${DEV_APP} already exists (URL: https://${FQDN})."
    exit 0
  fi
  echo "Removing broken or incomplete app ${DEV_APP} (state=${STATE})..."
  az containerapp delete -n "$DEV_APP" -g "$RESOURCE_GROUP" --yes --output none
fi

ENV_ID="$(az containerapp show -n "$PROD_APP" -g "$RESOURCE_GROUP" --query properties.managedEnvironmentId -o tsv)"
REGISTRY_SERVER="${ACR_NAME}.azurecr.io"
# Bootstrap from a prod tag in ACR (override with BOOTSTRAP_TAG, else newest tag, else v1).
BOOT_TAG="${BOOTSTRAP_TAG:-}"
if [ -z "$BOOT_TAG" ]; then
  BOOT_TAG="$(az acr repository show-tags -n "$ACR_NAME" --repository "$PROD_IMAGE_REPO" --orderby time_desc --top 1 -o tsv 2>/dev/null | head -1 | tr -d '\r')"
  if [ -z "$BOOT_TAG" ]; then
    BOOT_TAG="v1"
  fi
fi
INITIAL_IMAGE="${REGISTRY_SERVER}/${PROD_IMAGE_REPO}:${BOOT_TAG}"
echo "Initial revision image: ${INITIAL_IMAGE}"

REGISTRY_USER="$(az acr credential show -n "$ACR_NAME" --query username -o tsv)"
REGISTRY_PASSWORD="$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)"

echo "Creating ${DEV_APP} in environment ${ENV_ID}"
az containerapp create \
  --name "$DEV_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_ID" \
  --image "$INITIAL_IMAGE" \
  --registry-server "$REGISTRY_SERVER" \
  --registry-username "$REGISTRY_USER" \
  --registry-password "$REGISTRY_PASSWORD" \
  --ingress external \
  --target-port 8000 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 2 \
  --output none

FQDN="$(az containerapp show -n "$DEV_APP" -g "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)"
echo "Dev app URL: https://${FQDN}"
