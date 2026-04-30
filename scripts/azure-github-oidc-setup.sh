#!/usr/bin/env bash
# One-time: create an Azure AD app + federated GitHub credential and grant deploy rights.
# After this, add GitHub repo secrets:
#   AZURE_CLIENT_ID    = value printed as CLIENT_ID (same as app ID)
#   AZURE_TENANT_ID    = az account show --query tenantId -o tsv
#   AZURE_SUBSCRIPTION_ID = az account show --query id -o tsv
#
# Usage:
#   chmod +x scripts/azure-github-oidc-setup.sh
#   ./scripts/azure-github-oidc-setup.sh
#
# Customize if your fork uses a different remote:
set -euo pipefail

GITHUB_ORG="${GITHUB_ORG:-jack0lantern}"
GITHUB_REPO="${GITHUB_REPO:-alcohol-label-checker}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-alcohol-label-checker}"
APP_DISPLAY_NAME="${APP_DISPLAY_NAME:-github-actions-alcohol-label-checker}"

SUB="$(az account show --query id -o tsv)"
TENANT="$(az account show --query tenantId -o tsv)"
echo "Using subscription: $SUB (tenant $TENANT)"

RG_SCOPE="/subscriptions/${SUB}/resourceGroups/${RESOURCE_GROUP}"
if ! az group show -n "$RESOURCE_GROUP" &>/dev/null; then
  echo "Error: resource group ${RESOURCE_GROUP} not found. Create the Azure stack first or set RESOURCE_GROUP."
  exit 1
fi

echo "Creating app registration: $APP_DISPLAY_NAME"
APP_ID="$(az ad app create --display-name "$APP_DISPLAY_NAME" --query appId -o tsv)"
if ! az ad sp show --id "$APP_ID" &>/dev/null; then
  az ad sp create --id "$APP_ID"
fi

CRED_NAME="github-${GITHUB_REPO}-main"
SUBJECT="repo:${GITHUB_ORG}/${GITHUB_REPO}:ref:refs/heads/main"
PARAMS="$(mktemp)"
trap 'rm -f "$PARAMS"' EXIT
# shellcheck disable=SC2086
cat >"$PARAMS" <<EOF
{
  "name": "$CRED_NAME",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "$SUBJECT",
  "description": "GitHub Actions deploy from main",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF

echo "Adding federated credential (subject: $SUBJECT)"
az ad app federated-credential create --id "$APP_ID" --parameters "@${PARAMS}"

echo "Granting Contributor on $RESOURCE_GROUP (deploy + ACR push + container app update)"
az role assignment create \
  --assignee "$APP_ID" \
  --role Contributor \
  --scope "$RG_SCOPE" \
  &>/dev/null || echo "Note: role assignment may already exist; ignore if so."

echo ""
echo "Add these GitHub Actions secrets in ${GITHUB_ORG}/${GITHUB_REPO} (Settings -> Secrets and variables -> Actions):"
echo "  AZURE_CLIENT_ID=$APP_ID"
echo "  AZURE_TENANT_ID=$TENANT"
echo "  AZURE_SUBSCRIPTION_ID=$SUB"
echo ""
echo "Optional: add a second federated credential for workflow_dispatch from a feature branch (see Azure docs) if needed."
