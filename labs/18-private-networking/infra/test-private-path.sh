#!/usr/bin/env bash
# Tests the private path to your gateway from a VM inside the virtual network.
# Uses `az vm run-command invoke`, so the VM needs no public IP, no SSH session, and no gateway key.
# It runs jumpbox-check.sh on the VM: DNS lookup of the gateway host, then one HTTPS request.
#
# Usage:
#   export AI_GATEWAY_URL="https://<gateway>.azure-api.net"
#   ./test-private-path.sh <resource-group> <vm-name>
set -euo pipefail

RG="${1:?Pass the resource group of the jumpbox VM}"
VM="${2:?Pass the name of the jumpbox VM}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to https://<gateway>.azure-api.net}"

HOST="${AI_GATEWAY_URL#https://}"
HOST="${HOST%%/*}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Running checks for $HOST on $VM (this takes about a minute)..."
az vm run-command invoke -g "$RG" -n "$VM" --command-id RunShellScript \
  --scripts "@$SCRIPT_DIR/jumpbox-check.sh" --parameters "$HOST" \
  --query "value[0].message" -o tsv
