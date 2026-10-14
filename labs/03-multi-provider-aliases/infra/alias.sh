#!/usr/bin/env bash
# Lists, creates, retargets, and deletes AI Gateway model aliases with the REST API.
# The Azure CLI aigateway extension has no alias commands, so this script wraps `az rest`.
#
# Usage:
#   export RG="<resource-group>" GATEWAY="<gateway>"
#   ./alias.sh list
#   ./alias.sh show     <alias>
#   ./alias.sh put      <alias> <provider-name> <backend-model> [tokens-per-minute]
#   ./alias.sh retarget <alias> <provider-name> <backend-model>
#   ./alias.sh delete   <alias>
#
# "put" creates or replaces the whole alias, including its policies. With tokens-per-minute it adds a
# per-caller token limit to the alias. "retarget" sends a PATCH with only backendModels, so the alias
# name, description, and policies stay as they are.
# Requires the Azure CLI (signed in), the aigateway extension, and jq.
set -euo pipefail

: "${RG:?Set RG to the gateway resource group}"
: "${GATEWAY:?Set GATEWAY to the gateway name}"

ACTION="${1:-list}"
API="api-version=2025-09-01-preview"
GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
WS_ID="$GATEWAY_ID/workspaces/default"
ARM="https://management.azure.com"

list_json() { az rest --method get --url "$ARM$WS_ID/aliases?$API" -o json; }

# The callable alias lives in properties.aliasName and can contain "/". The resource name can't, so look
# up an existing alias by its callable name first, and otherwise derive a resource name from it.
resource_name() {
  local found
  found="$(list_json | jq -r --arg a "$1" '.value[] | select((.properties.aliasName // .name) == $a) | .name' | head -n1)"
  if [ -n "$found" ]; then echo "$found"; return; fi
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's#[^a-z0-9_.-]+#-#g; s#^[-.]+##; s#[-.]+$##'
}

model_id() { echo "$WS_ID/modelProviders/$1/models/$2"; }

print_table() {
  jq -r '(if has("value") then .value[] else . end)
    | [ (.properties.aliasName // .name),
        (.properties.backendModels[0].resourceId // "-" | split("/") | if length > 2 then "\(.[-3])/\(.[-1])" else .[0] end),
        ((.properties.policies // []) | map(if .type == "tokenLimit" then "tokenLimit \(.count)/\(.period)" else .type end) | join(", ") | if . == "" then "-" else . end) ]
    | @tsv' | { printf 'ALIAS\tPROVIDER/BACKEND MODEL\tALIAS POLICIES\n'; cat; } | column -t -s $'\t'
}

case "$ACTION" in
  list)
    list_json | print_table
    ;;
  show)
    ALIAS="${2:?Pass the alias}"
    az rest --method get --url "$ARM$WS_ID/aliases/$(resource_name "$ALIAS")?$API"
    ;;
  put)
    ALIAS="${2:?Pass the alias}"
    PROVIDER="${3:?Pass the model provider name}"
    MODEL="${4:?Pass the backend model name}"
    TPM="${5:-}"
    BODY="$(jq -cn --arg alias "$ALIAS" --arg id "$(model_id "$PROVIDER" "$MODEL")" --arg tpm "$TPM" '
      {properties: {
        aliasName: $alias,
        backendModels: [{resourceId: $id}],
        policies: (if $tpm == "" then [] else
          [{type: "tokenLimit", count: ($tpm | tonumber), period: "minute", counterKey: "Identity"}] end)}}')"
    NAME="$(resource_name "$ALIAS")"
    az rest --method put --url "$ARM$WS_ID/aliases/$NAME?$API" --body "$BODY" -o none
    az rest --method get --url "$ARM$WS_ID/aliases/$NAME?$API" -o json | print_table
    ;;
  retarget)
    ALIAS="${2:?Pass the alias}"
    PROVIDER="${3:?Pass the model provider name}"
    MODEL="${4:?Pass the backend model name}"
    BODY="$(jq -cn --arg id "$(model_id "$PROVIDER" "$MODEL")" '{properties: {backendModels: [{resourceId: $id}]}}')"
    NAME="$(resource_name "$ALIAS")"
    az rest --method patch --url "$ARM$WS_ID/aliases/$NAME?$API" --body "$BODY" -o none
    az rest --method get --url "$ARM$WS_ID/aliases/$NAME?$API" -o json | print_table
    ;;
  delete)
    ALIAS="${2:?Pass the alias}"
    az rest --method delete --url "$ARM$WS_ID/aliases/$(resource_name "$ALIAS")?$API"
    echo "Deleted alias $ALIAS"
    ;;
  *)
    echo "Unknown action '$ACTION'. Use list, show, put, retarget, or delete." >&2
    exit 2
    ;;
esac
