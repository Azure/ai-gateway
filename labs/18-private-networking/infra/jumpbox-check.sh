#!/usr/bin/env bash
# Runs ON the jumpbox VM through `az vm run-command invoke`. Don't run it on your workstation.
# Resolves the gateway host name and sends one HTTPS request without credentials. Any HTTP status code
# (for example 401) proves the VM reached the gateway; "HTTP 000" means DNS or the network path failed.
#
# Usage (from test-private-path.sh / .ps1):
#   az vm run-command invoke ... --scripts @jumpbox-check.sh --parameters <gateway-host-name>
set -eu
# Run Command can start the script with a POSIX shell, so only turn on pipefail when bash runs it.
if [ -n "${BASH_VERSION:-}" ]; then set -o pipefail; fi
host="${1:?Pass the gateway host name, for example <gateway>.azure-api.net}"

echo "== DNS: $host"
if command -v nslookup >/dev/null 2>&1; then
  nslookup "$host" || echo "DNS lookup failed for $host"
else
  getent hosts "$host" || echo "DNS lookup failed for $host"
fi

echo "== HTTPS: POST https://$host/default/models/openai/v1/chat/completions (no credentials)"
curl -sS -o /dev/null --max-time 20 -X POST \
  -H "Content-Type: application/json" -d '{}' \
  -w 'HTTP %{http_code} from %{remote_ip}\n' \
  "https://$host/default/models/openai/v1/chat/completions" || true
