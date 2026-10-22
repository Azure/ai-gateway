#!/usr/bin/env bash

set -euo pipefail
set +x

readonly API_VERSION="2024-05-01"
readonly FIXTURE_KIND="apimMigrationV2"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

usage() {
  cat <<'EOF'
Provision or remove an isolated APIM V2 migration fixture.

Usage:
  provision.sh provision --subscription ID --location REGION --service-name NAME
      [--resource-group NAME] [--sku BasicV2|StandardV2|PremiumV2]
  provision.sh cleanup --subscription ID --service-name NAME
      [--resource-group NAME]

The resource group must not exist before provisioning. Cleanup deletes it only
when both fixture ownership tags match the requested service.
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_value() {
  [[ $# -ge 2 && -n "$2" ]] || die "$1 requires a value"
}

[[ $# -gt 0 ]] || {
  usage
  exit 2
}
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  usage
  exit 0
fi

ACTION="$1"
shift
SUBSCRIPTION=""
LOCATION=""
SERVICE_NAME=""
RESOURCE_GROUP=""
SKU="BasicV2"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subscription)
      require_value "$@"
      SUBSCRIPTION="$2"
      shift 2
      ;;
    --location)
      require_value "$@"
      LOCATION="$2"
      shift 2
      ;;
    --service-name)
      require_value "$@"
      SERVICE_NAME="$2"
      shift 2
      ;;
    --resource-group)
      require_value "$@"
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --sku)
      require_value "$@"
      SKU="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ "$ACTION" == "provision" || "$ACTION" == "cleanup" ]] \
  || die "action must be provision or cleanup"
[[ -n "$SUBSCRIPTION" ]] || die "--subscription is required"
[[ "$SUBSCRIPTION" =~ ^[0-9a-fA-F-]{36}$ ]] \
  || die "--subscription must be a subscription UUID"
[[ "$SERVICE_NAME" =~ ^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$ ]] \
  || die "--service-name must be 2-50 lowercase letters, numbers, or hyphens"

if [[ -z "$RESOURCE_GROUP" ]]; then
  RESOURCE_GROUP="rg-${SERVICE_NAME}"
fi
[[ "$RESOURCE_GROUP" =~ ^[A-Za-z0-9._-]+$ ]] \
  || die "--resource-group may contain only letters, numbers, '.', '_', and '-'"
[[ "$SKU" == "BasicV2" || "$SKU" == "StandardV2" || "$SKU" == "PremiumV2" ]] \
  || die "--sku must be BasicV2, StandardV2, or PremiumV2"

command -v az >/dev/null 2>&1 || die "Azure CLI (az) is required"
command -v python3 >/dev/null 2>&1 || die "Python 3 is required"

readonly SERVICE_ID="/subscriptions/${SUBSCRIPTION}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${SERVICE_NAME}"
readonly ARM="https://management.azure.com"

az_cli() {
  az "$@" --subscription "$SUBSCRIPTION" --only-show-errors
}

rest_put() {
  local resource_path="$1"
  local body="$2"
  az_cli rest \
    --method put \
    --url "${ARM}${resource_path}?api-version=${API_VERSION}" \
    --body "$body" \
    --output none
}

cleanup() {
  local group_json fixture_kind fixture_service

  if [[ "$(az_cli group exists --name "$RESOURCE_GROUP" --output tsv)" != "true" ]]; then
    printf 'Resource group %s does not exist; nothing to clean up.\n' "$RESOURCE_GROUP"
    return
  fi

  group_json="$(az_cli group show --name "$RESOURCE_GROUP" --output json)"
  fixture_kind="$(
    python3 -c 'import json,sys; print((json.load(sys.stdin).get("tags") or {}).get("fixtureKind", ""))' \
      <<<"$group_json"
  )"
  fixture_service="$(
    python3 -c 'import json,sys; print((json.load(sys.stdin).get("tags") or {}).get("fixtureService", ""))' \
      <<<"$group_json"
  )"

  [[ "$fixture_kind" == "$FIXTURE_KIND" ]] \
    || die "refusing cleanup: resource group lacks fixtureKind=$FIXTURE_KIND"
  [[ "$fixture_service" == "$SERVICE_NAME" ]] \
    || die "refusing cleanup: fixtureService tag does not match $SERVICE_NAME"

  az_cli group delete --name "$RESOURCE_GROUP" --yes --output none
  printf 'Deleted fixture resource group %s.\n' "$RESOURCE_GROUP"
}

if [[ "$ACTION" == "cleanup" ]]; then
  cleanup
  exit 0
fi

[[ -n "$LOCATION" ]] || die "--location is required for provisioning"
[[ "$LOCATION" =~ ^[a-z0-9-]+$ ]] \
  || die "--location must be an Azure region name"
[[ "$(az_cli group exists --name "$RESOURCE_GROUP" --output tsv)" == "false" ]] \
  || die "resource group $RESOURCE_GROUP already exists; choose a new fixture name"

printf 'Creating isolated fixture resource group %s...\n' "$RESOURCE_GROUP"
az_cli group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags "fixtureKind=${FIXTURE_KIND}" "fixtureService=${SERVICE_NAME}" \
  --output none

service_body="$(
  printf '{"location":"%s","sku":{"name":"%s","capacity":1},"identity":{"type":"SystemAssigned"},"properties":{"publisherEmail":"fixture@example.invalid","publisherName":"AI Gateway migration fixture"},"tags":{"fixtureKind":"%s","fixtureService":"%s"}}' \
    "$LOCATION" "$SKU" "$FIXTURE_KIND" "$SERVICE_NAME"
)"

printf 'Creating %s APIM service %s (this can take over an hour)...\n' \
  "$SKU" "$SERVICE_NAME"
rest_put "$SERVICE_ID" "$service_body"

for _ in {1..480}; do
  state="$(
    az_cli rest \
      --method get \
      --url "${ARM}${SERVICE_ID}?api-version=${API_VERSION}" \
      --query properties.provisioningState \
      --output tsv
  )"
  case "$state" in
    Succeeded)
      break
      ;;
    Failed|Canceled)
      die "APIM provisioning entered terminal state: $state"
      ;;
  esac
  sleep 15
done
[[ "${state:-}" == "Succeeded" ]] \
  || die "timed out waiting for APIM provisioning; retain the group for diagnosis"

printf 'Creating representative non-secret APIM assets...\n'
rest_put \
  "${SERVICE_ID}/policies/policy" \
  "@${SCRIPT_DIR}/service-policy.json"
rest_put \
  "${SERVICE_ID}/namedValues/fixture-label" \
  '{"properties":{"displayName":"Fixture label","secret":false,"value":"non-secret-fixture-value","tags":["migration-fixture"]}}'
rest_put \
  "${SERVICE_ID}/policyFragments/fixture-fragment" \
  "@${SCRIPT_DIR}/policy-fragment.json"
rest_put \
  "${SERVICE_ID}/backends/example-backend" \
  '{"properties":{"protocol":"http","url":"https://example.com"}}'
rest_put \
  "${SERVICE_ID}/apis/example-api" \
  '{"properties":{"displayName":"Example REST API","path":"example","protocols":["https"],"serviceUrl":"https://example.com","subscriptionRequired":false,"type":"http"}}'
rest_put \
  "${SERVICE_ID}/apis/example-api/operations/get-example" \
  '{"properties":{"displayName":"Get example","method":"GET","urlTemplate":"/","responses":[{"statusCode":200,"description":"Fixture response"}]}}'
rest_put \
  "${SERVICE_ID}/apis/example-api/policies/policy" \
  "@${SCRIPT_DIR}/api-policy.json"
rest_put \
  "${SERVICE_ID}/products/fixture-product" \
  '{"properties":{"displayName":"Fixture product","description":"Non-secret migration fixture product","subscriptionRequired":false,"approvalRequired":false,"state":"published"}}'
rest_put \
  "${SERVICE_ID}/products/fixture-product/apis/example-api" \
  '{}'
rest_put \
  "${SERVICE_ID}/workspaces/fixture-workspace" \
  '{"properties":{"displayName":"Fixture workspace","description":"Migration inventory workspace fixture"}}'
rest_put \
  "${SERVICE_ID}/workspaces/fixture-workspace/backends/workspace-backend" \
  '{"properties":{"protocol":"http","url":"https://example.org"}}'
rest_put \
  "${SERVICE_ID}/workspaces/fixture-workspace/apis/workspace-api" \
  '{"properties":{"displayName":"Workspace REST API","path":"workspace-example","protocols":["https"],"serviceUrl":"https://example.org","subscriptionRequired":false,"type":"http"}}'
rest_put \
  "${SERVICE_ID}/workspaces/fixture-workspace/apis/workspace-api/operations/get-workspace-example" \
  '{"properties":{"displayName":"Get workspace example","method":"GET","urlTemplate":"/","responses":[{"statusCode":200,"description":"Fixture response"}]}}'

cat <<EOF
Fixture is ready.
Source resource ID:
${SERVICE_ID}

Inventory it without writing credentials:
az ai-gateway import-inventory --source-apim-id '${SERVICE_ID}' --output json

Remove only this tagged fixture:
${SCRIPT_DIR}/provision.sh cleanup --subscription '${SUBSCRIPTION}' --service-name '${SERVICE_NAME}' --resource-group '${RESOURCE_GROUP}'
EOF
