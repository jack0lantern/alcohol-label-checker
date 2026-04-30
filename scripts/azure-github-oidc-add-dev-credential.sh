#!/usr/bin/env bash
# Add OIDC federated credential for the dev branch (refs/heads/dev) to an existing
# app registration used by GitHub Actions. Run once if you already set up prod OIDC for main only.
#
# Usage:
#   export AZURE_CLIENT_ID=<same as GitHub secret AZURE_CLIENT_ID>
#   ./scripts/azure-github-oidc-add-dev-credential.sh
#
# Or: ./scripts/azure-github-oidc-add-dev-credential.sh <app-client-id>

set -euo pipefail

GITHUB_ORG="${GITHUB_ORG:-jack0lantern}"
GITHUB_REPO="${GITHUB_REPO:-alcohol-label-checker}"

APP_ID="${1:-${AZURE_CLIENT_ID:-}}"
if [ -z "$APP_ID" ]; then
  echo "Set AZURE_CLIENT_ID or pass app (client) ID as first argument."
  exit 1
fi

CRED_NAME="github-${GITHUB_REPO}-dev"
SUBJECT="repo:${GITHUB_ORG}/${GITHUB_REPO}:ref:refs/heads/dev"
PARAMS="$(mktemp)"
trap 'rm -f "$PARAMS"' EXIT

cat >"$PARAMS" <<EOF
{
  "name": "$CRED_NAME",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "$SUBJECT",
  "description": "GitHub Actions deploy from dev",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF

echo "Adding federated credential for subject: $SUBJECT"
az ad app federated-credential create --id "$APP_ID" --parameters "@${PARAMS}"
echo "Done. Pushes to dev can authenticate to Azure with the same AZURE_CLIENT_ID secret."
