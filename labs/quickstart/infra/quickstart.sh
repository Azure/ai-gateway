#!/usr/bin/env bash
# Azure AI Gateway quick start: deploys a gateway with a published Foundry model in one deployment, reads the
# runtime API key without printing it, and makes the first model call. Takes about five minutes.
#
# Usage, from labs/quickstart:
#   ./infra/quickstart.sh [resource-group] [location]
# Defaults: rg-aigw-quickstart in eastus2. Requires the Azure CLI (signed in with az login), curl, and jq.
set -euo pipefail

RG="${1:-rg-aigw-quickstart}"
LOCATION="${2:-eastus2}"
API="api-version=2025-09-01-preview"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECONDS=0

SUBSCRIPTION="$(az account show --query name -o tsv 2>/dev/null)" || { echo "Sign in first: az login" >&2; exit 1; }
echo "Subscription: $SUBSCRIPTION"

echo "[1/3] Deploying a gateway and a Foundry model to $RG in $LOCATION. This takes about 3 minutes..."
az group create --name "$RG" --location "$LOCATION" --output none
OUTPUTS="$(az deployment group create --resource-group "$RG" --name quickstart \
  --template-file "$HERE/main.bicep" --parameters location="$LOCATION" \
  --query properties.outputs --output json --only-show-errors)"
out() { jq -r ".$1.value" <<<"$OUTPUTS"; }
GATEWAY_ID="$(out gatewayId)"
KEY_NAME="$(out apiKeyName)"
AI_GATEWAY_URL="$(out gatewayUrl)"
AI_GATEWAY_MODEL="$(out aliasName)"
echo "      Gateway $(out gatewayName) is ready at $AI_GATEWAY_URL"

echo "[2/3] Reading the runtime key $KEY_NAME. The script doesn't print it."
AI_GATEWAY_API_KEY="$(az rest --method post \
  --url "https://management.azure.com$GATEWAY_ID/apiKeys/$KEY_NAME/listSecrets?$API" \
  --query primaryKey --output tsv)"

echo "[3/3] Calling $AI_GATEWAY_MODEL through the gateway"
BODY="$(jq -n --arg m "$AI_GATEWAY_MODEL" \
  '{model: $m, messages: [{role: "user", content: "In one sentence, what does an AI gateway do?"}]}')"
MAX_ATTEMPTS=18
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  RESPONSE="$(curl -sS -w '\n%{http_code}' "$AI_GATEWAY_URL/default/models/openai/v1/chat/completions" \
    -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY")"
  STATUS="${RESPONSE##*$'\n'}"
  RESPONSE="${RESPONSE%$'\n'*}"
  [[ "$STATUS" == 200 ]] && break
  # A new key, alias, or role assignment can take a minute to apply.
  if [[ "$STATUS" =~ ^(401|403|404)$ && "$attempt" -lt "$MAX_ATTEMPTS" ]]; then
    echo "      HTTP $STATUS while the new settings apply. Retrying in 10 seconds..."
    sleep 10
    continue
  fi
  echo "HTTP $STATUS: $RESPONSE" >&2
  exit 1
done

echo
echo "HTTP 200 from $(jq -r .model <<<"$RESPONSE"):"
echo "  $(jq -r '.choices[0].message.content' <<<"$RESPONSE")"
echo
echo "Done in $((SECONDS / 60)) min $((SECONDS % 60)) s."
echo "  Model endpoint  $(out modelEndpoint)"
echo "  Alias           $AI_GATEWAY_MODEL"
echo "  Portal          https://ai.gateway.azure.com"
echo
echo "Use the gateway from your shell:"
echo "  export AI_GATEWAY_URL=\"$AI_GATEWAY_URL\" AI_GATEWAY_MODEL=\"$AI_GATEWAY_MODEL\""
echo "  export AI_GATEWAY_API_KEY=\"\$(az rest --method post --url \"https://management.azure.com$GATEWAY_ID/apiKeys/$KEY_NAME/listSecrets?$API\" --query primaryKey -o tsv)\""
echo
echo "Clean up when you're done:"
echo "  az group delete --name $RG --yes"
echo "  az cognitiveservices account purge --name $(out foundryAccountName) --resource-group $RG --location $LOCATION"
