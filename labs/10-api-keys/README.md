---
title: Issue and rotate runtime API keys
summary: Give every app its own runtime API key, keep the value out of your code, rotate it without downtime with the primary and secondary values, revoke a leaked key, and see usage and cost per key in Monitoring.
category: security
level: Beginner
duration: 15
tracks: [portal, cli]
order: 10
illustration: diagrams/identity-boundaries.svg
tags: [API keys, rotation, revocation, Key Vault, secrets, cost attribution, runtime access]
objectives:
  - Create one runtime API key for each app and keep its value in a secret store, not in code
  - Rotate a key without downtime by moving clients between its primary and secondary values
  - Revoke a leaked key and confirm that the gateway rejects it with 401
  - Find usage and estimated cost for each key in Monitoring
  - Decide when to replace API keys with Microsoft Entra ID
prereqs:
  - 01-provision-gateway
---

# Issue and rotate runtime API keys

Three callers now use your gateway: the `app-dev` web app, the `support-bot` agent, and a data scientist's
notebook that was shared with the whole company, key included. In this lab you give each caller its own runtime
API key, keep the values in a secret store, rotate the bot's key without taking it offline, and revoke the
leaked notebook key. Because every key is a separate caller identity, you can also see who used what.

![Callers reach the gateway with an API key or a Microsoft Entra token, and the gateway reaches providers with its own credentials](../assets/diagrams/identity-boundaries.svg "Inbound, apps send an api-key header or a Microsoft Entra token. Outbound, the gateway uses its managed identity or a provider key that it stores. Callers never receive backend credentials.")

<!-- widget: request-lifecycle {"focus":"auth"} -->

## Before you begin

- Complete [Provision your AI Gateway](../01-provision-gateway/README.md). You need the gateway, its resource
  group, and its runtime URL.
- Recommended: complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md),
  so you have a model alias to call. The checks in this lab call that alias. The gateway answers `404` for an
  alias it doesn't know before it checks the key, so without a real alias the checks can't tell accepted keys
  from rejected keys.
- Permission to manage the gateway's keys, for example **Contributor** on its resource group. Reading a key
  value needs `Microsoft.ApiManagement/aigateways/apiKeys/listSecrets/action`, which **Contributor** includes.
- Optional: an Azure Key Vault that uses Azure RBAC, where you have **Key Vault Secrets Officer**. You can create
  one below.
- Optional, for usage and cost per key: monitoring configured in
  [Monitor usage, cost, and traces](../13-monitoring/README.md).
- For the CLI track and the **Verify** scripts: the
  [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with `az login`.
  The CLI track calls the Azure Resource Manager REST API with `az rest`, because the `az aigateway` extension
  doesn't manage the new `aigateways` resource type yet. The Bash scripts use `curl`; the PowerShell scripts need
  PowerShell 7 or later.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export AI_GATEWAY_MODEL="<model-alias>"      # an alias you can call, for example the one from lab 02
# export KEY_VAULT="<key-vault>"             # optional: uncomment to keep key values in Key Vault

export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(az resource show -g "$RG" -n "$GATEWAY" --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv)"
export GW="https://management.azure.com$GATEWAY_ID"
export AI_GATEWAY_URL="https://$(az resource show --ids "$GATEWAY_ID" --query properties.frontend.defaultHostname -o tsv)"
```

```powershell title="PowerShell"
$RG                   = "<resource-group>"
$GATEWAY              = "<gateway>"
$env:AI_GATEWAY_MODEL = "<model-alias>"      # an alias you can call, for example the one from lab 02
# $KEY_VAULT          = "<key-vault>"        # optional: uncomment to keep key values in Key Vault

$API        = "api-version=2025-09-01-preview"
$GATEWAY_ID = az resource show -g $RG -n $GATEWAY --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv
$GW         = "https://management.azure.com$GATEWAY_ID"
$env:AI_GATEWAY_URL = "https://$(az resource show --ids $GATEWAY_ID --query properties.frontend.defaultHostname -o tsv)"
```

<details>
<summary>No Key Vault yet? Create one for this lab.</summary>

Key Vault names are globally unique, 3 to 24 characters. The vault uses Azure RBAC, and you get
**Key Vault Secrets Officer** so you can write and read secrets. A new role assignment can take a few minutes to
apply.

```bash title="Bash"
export KEY_VAULT="kv-aigw-$RANDOM"
az keyvault create -g "$RG" -n "$KEY_VAULT" --enable-rbac-authorization true -o none
az role assignment create --role "Key Vault Secrets Officer" \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --scope "$(az keyvault show -n "$KEY_VAULT" --query id -o tsv)" -o none
```

```powershell title="PowerShell"
$KEY_VAULT = "kv-aigw-$(Get-Random -Maximum 99999)"
az keyvault create -g $RG -n $KEY_VAULT --enable-rbac-authorization true -o none
az role assignment create --role "Key Vault Secrets Officer" `
  --assignee (az ad signed-in-user show --query id -o tsv) `
  --scope (az keyvault show -n $KEY_VAULT --query id -o tsv) -o none
```

</details>

## How it works

A runtime API key is a gateway resource with a name and two values, **primary** and **secondary**.
Both values work at the same time, which is what makes rotation without downtime possible. Clients send either
value in the `api-key` header. The model endpoint also accepts it as a bearer token, which is how OpenAI SDKs
send their API key, but a request with both headers gets `400`. The gateway validates the key before it applies
policies or forwards the request, so a missing, wrong, rotated, or deleted value, or a suspended key, gets
`401 Unauthorized` and never reaches a model.

A key is gateway-scoped: it grants access to every published model and MCP server on the gateway. Each key is
also a separate caller identity, which token limits, cost limits, and Monitoring use to tell callers apart.
That's why every app, agent, or user should get its own key.

| Task | Portal (**Access** › **Keys**) | Azure CLI (`az rest` on `$GW/apiKeys/<name>`) |
|---|---|---|
| Create a key | **Create API key** | `PUT` |
| Read a value | **View keys** (primary value) | `POST .../listSecrets` (primary and secondary values) |
| Rotate | **Rotate key** (primary value) | `POST .../regeneratePrimaryKey` or `.../regenerateSecondaryKey` |
| Block temporarily | — | `PATCH` with `state` set to `suspended`, then back to `active` |
| Revoke | **Delete** | `DELETE` |

The gateway also has a built-in key named `master`. Don't hand it out; create named keys instead.

## Create a key for each app

Create three keys: `app-dev` for the web app, `support-bot` for the agent, and `old-notebook`, which stands in
for the key that leaked. Pick one track.

<!-- track: portal | Portal -->

### Create the first key

1. In the [AI Gateway portal](https://ai.gateway.azure.com), open your gateway and select **Access** › **Keys**.
2. Select **Create API key**.
3. In **Key name**, enter `app-dev`, and select **Create**.
4. The **API key created successfully** dialog shows the value. Select **Copy & done**.

Store the value right away; the next section shows where. After you close the dialog, only people with the
`apiKeys/listSecrets/action` permission, such as Contributors, can display the value again, with **View keys**.

### Create the other two keys

Repeat the steps for `support-bot` and `old-notebook`. Names must be unique, ignoring case; a duplicate gets
`A key named "..." already exists.` The portal derives the key's resource name from **Key name**: lowercase, with
every character other than letters, digits, and hyphens replaced by `-`. Use that resource name with the CLI.

### Load a value in your shell

Select the **…** (**More actions**) button on the `app-dev` row, select **View keys**, and copy the value. Paste it
into your shell for the checks in this lab:

```bash title="Bash"
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

<!-- track: cli | Azure CLI -->

### Create the keys

The key's name is the last segment of its URL, and the body can be empty. The service sets the key's display
name itself, so identify keys by `name`.

```bash title="Bash"
for KEY in app-dev support-bot old-notebook; do
  az rest --method put --url "$GW/apiKeys/$KEY?$API" --body '{"properties":{}}' -o none
done
az rest --url "$GW/apiKeys?$API" --query "value[].{name:name, state:properties.state}" -o table
```

```powershell title="PowerShell"
'{"properties":{}}' | Set-Content apikey.json
foreach ($key in "app-dev", "support-bot", "old-notebook") {
  az rest --method put --url "$GW/apiKeys/$key`?$API" --body "@apikey.json" -o none
}
Remove-Item apikey.json
az rest --url "$GW/apiKeys?$API" --query "value[].{name:name, state:properties.state}" -o table
```

The list also shows the built-in `master` key, and every key is `active`. `PUT` and `GET` never return key
values.

### Load a value in your shell

The `listSecrets` action returns `primaryKey` and `secondaryKey`. Capture the value in a variable instead of
printing it:

```bash title="Bash"
export AI_GATEWAY_API_KEY="$(az rest --method post --url "$GW/apiKeys/app-dev/listSecrets?$API" \
  --query primaryKey -o tsv)"
```

```powershell title="PowerShell"
$env:AI_GATEWAY_API_KEY = az rest --method post --url "$GW/apiKeys/app-dev/listSecrets?$API" `
  --query primaryKey -o tsv
```

<!-- /tracks -->

From the lab folder, send one request with the `app-dev` key:

```bash title="Bash"
./infra/check-key.sh app-dev
```

```powershell title="PowerShell"
./infra/check-key.ps1 -Label app-dev
```

The script sends a tiny Chat Completions request and prints only the last four characters of the key. On GitHub,
open [check-key.sh](infra/check-key.sh) or [check-key.ps1](infra/check-key.ps1).

<!-- include: infra/check-key.sh -->

> **Checkpoint**
> **Access** › **Keys** lists `app-dev`, `support-bot`, and `old-notebook`, and the check prints
> `HTTP 200  accepted` for `app-dev`.

## Store the key outside your code

A runtime key opens every model and MCP server on the gateway, so treat it like a password:

- **Local development:** set an environment variable for the session, as in this lab, and read it in code, for
  example `os.environ["AI_GATEWAY_API_KEY"]` in Python. If you keep it in a `.env` file, add the file to
  `.gitignore`.
- **Hosted apps:** keep the value in Azure Key Vault. App Service and Azure Functions resolve
  [Key Vault references](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) in app
  settings, and Azure Container Apps can
  [reference Key Vault secrets](https://learn.microsoft.com/azure/container-apps/manage-secrets).
- **Pipelines:** use the secret store of your CI system, or read the value from Key Vault at run time.
- **Never** put the value in source code, a committed `.env` file, build logs, notebooks, chat, or tickets.

If you set `KEY_VAULT`, store the `app-dev` and `support-bot` values there. The commands print only the secret
IDs. Each secret is named `<key>-api-key`, which is the name the rotation script updates later.

```bash title="Bash"
for KEY in app-dev support-bot; do
  az keyvault secret set --vault-name "$KEY_VAULT" -n "$KEY-api-key" \
    --value "$(az rest --method post --url "$GW/apiKeys/$KEY/listSecrets?$API" --query primaryKey -o tsv)" \
    --tags aigateway-key="$KEY" key-type=primary --query id -o tsv
done
```

```powershell title="PowerShell"
foreach ($key in "app-dev", "support-bot") {
  $value = az rest --method post --url "$GW/apiKeys/$key/listSecrets?$API" --query primaryKey -o tsv
  az keyvault secret set --vault-name $KEY_VAULT -n "$key-api-key" --value $value `
    --tags aigateway-key=$key key-type=primary --query id -o tsv
}
Remove-Variable value
```

An app, or you, then reads the value from the vault instead of from the gateway:

```bash title="Bash"
export AI_GATEWAY_API_KEY="$(az keyvault secret show --vault-name "$KEY_VAULT" -n app-dev-api-key --query value -o tsv)"
```

```powershell title="PowerShell"
$env:AI_GATEWAY_API_KEY = az keyvault secret show --vault-name $KEY_VAULT -n app-dev-api-key --query value -o tsv
```

> [!NOTE]
> The portal track can store the values the same way: run the commands above, or add the secrets to the vault in
> the Azure portal.

## Rotate a key without downtime

Rotate keys on a schedule, and whenever someone who had a value leaves the team. Regenerating a value invalidates
that value only, and right away. The trick is to regenerate the value that no client is using.

<!-- track: portal | Portal -->

### Save the current value

You use the old value later to prove that it stopped working. On the `support-bot` row, select **…**
(**More actions**) › **View keys**, copy the value, and paste it into your shell:

```bash title="Bash"
read -rsp "Current support-bot value: " OLD_SUPPORT_BOT && echo
```

```powershell title="PowerShell"
$OLD_SUPPORT_BOT = Read-Host "Current support-bot value" -MaskInput
```

### Rotate the key

1. On the `support-bot` row, select **…** (**More actions**) › **Rotate key**.
2. The `Rotate "support-bot" key?` dialog warns that the current value stops working immediately and that the
   new value is displayed once. Select **Rotate**.
3. In **API key rotated successfully**, copy the new value and update the client, or the `support-bot-api-key`
   secret in Key Vault.

> [!NOTE]
> The portal rotates the **primary** value in place, so a client that still sends the old value gets `401` until
> you update it. To rotate without downtime from the portal, replace the key instead: create `support-bot-v2`,
> move the client to it, and then delete `support-bot`. The new key is a new caller identity, so move any
> cost-limit overrides to it, and expect Monitoring to report it separately. The CLI track avoids both trade-offs
> with the secondary value.

<!-- track: cli | Azure CLI -->

### Save the current value

Clients use the primary value today. Keep it so you can prove later that it stopped working:

```bash title="Bash"
OLD_SUPPORT_BOT="$(az rest --method post --url "$GW/apiKeys/support-bot/listSecrets?$API" \
  --query primaryKey -o tsv)"
```

```powershell title="PowerShell"
$OLD_SUPPORT_BOT = az rest --method post --url "$GW/apiKeys/support-bot/listSecrets?$API" `
  --query primaryKey -o tsv
```

### Regenerate the unused secondary value

No client uses the secondary value, so regenerating it breaks nothing:

```bash title="Bash"
./infra/rotate-key.sh support-bot secondary
```

```powershell title="PowerShell"
./infra/rotate-key.ps1 -ResourceGroup $RG -Gateway $GATEWAY -KeyName support-bot -KeyType secondary # -KeyVault $KEY_VAULT
```

The script calls the key's `regenerateSecondaryKey` action with `az rest`, reads the new value with
`listSecrets`, and prints only its last four characters. If `KEY_VAULT` is set in Bash, or you pass `-KeyVault` in PowerShell,
it also writes the new value to the `support-bot-api-key` secret. On GitHub, open
[rotate-key.sh](infra/rotate-key.sh) or [rotate-key.ps1](infra/rotate-key.ps1).

<!-- include: infra/rotate-key.sh -->

### Move the client to the secondary value

Update the client's configuration to the new secondary value and restart it, or let it reload the Key Vault
secret. Both values are valid now, so no request fails during the switch. The old primary value still works:

```bash title="Bash"
AI_GATEWAY_API_KEY="$OLD_SUPPORT_BOT" ./infra/check-key.sh "old primary"
```

```powershell title="PowerShell"
./infra/check-key.ps1 -ApiKey $OLD_SUPPORT_BOT -Label "old primary"
```

### Regenerate the primary value

When every client uses the secondary value, regenerate the primary. This invalidates the old value, wherever it
might have been copied:

```bash title="Bash"
./infra/rotate-key.sh support-bot primary
```

```powershell title="PowerShell"
./infra/rotate-key.ps1 -ResourceGroup $RG -Gateway $GATEWAY -KeyName support-bot -KeyType primary # -KeyVault $KEY_VAULT
```

Next time, rotate in the other direction: regenerate the primary, move clients to it, then regenerate the
secondary. With Key Vault, the secret always holds the newest value, so clients that reload it move along
automatically.

<!-- /tracks -->

> **Checkpoint**
> `AI_GATEWAY_API_KEY="$OLD_SUPPORT_BOT" ./infra/check-key.sh "rotated value"` (or
> `./infra/check-key.ps1 -ApiKey $OLD_SUPPORT_BOT -Label "rotated value"`) prints `HTTP 401`.

## Revoke a leaked key

When a key leaks, revoke it first and investigate afterward. Deleting a key invalidates both of its values
immediately, and anyone who holds them gets `401`. Pick one track.

<!-- track: portal | Portal -->

### Save the leaked value

You use it to prove that the key no longer works. On the `old-notebook` row, select **…** (**More actions**) ›
**View keys**, copy the value, and paste it into your shell:

```bash title="Bash"
read -rsp "Leaked value: " LEAKED_KEY && echo
```

```powershell title="PowerShell"
$LEAKED_KEY = Read-Host "Leaked value" -MaskInput
```

### Delete the key

Select the check box on the `old-notebook` row, and then select **Delete**. The `Delete "old-notebook" key?`
dialog warns that applications using the key will no longer authenticate to the gateway and that the action
can't be undone. Select **Delete**.

<!-- track: cli | Azure CLI -->

### Save the leaked value and delete the key

```bash title="Bash"
LEAKED_KEY="$(az rest --method post --url "$GW/apiKeys/old-notebook/listSecrets?$API" \
  --query primaryKey -o tsv)"
az rest --method delete --url "$GW/apiKeys/old-notebook?$API"
```

```powershell title="PowerShell"
$LEAKED_KEY = az rest --method post --url "$GW/apiKeys/old-notebook/listSecrets?$API" `
  --query primaryKey -o tsv
az rest --method delete --url "$GW/apiKeys/old-notebook?$API"
```

### Suspend a key instead

To block a key while you investigate, without deleting it, set its `state` to `suspended`. Calls with the key
get `401` until you set it back to `active`. The **Verify** section expects `support-bot` to work, so set it
back to `active` before you continue:

```bash title="Bash"
az rest --method patch --url "$GW/apiKeys/support-bot?$API" \
  --body '{"properties":{"state":"suspended"}}' --query properties.state -o tsv
# Later, to let the key work again:
az rest --method patch --url "$GW/apiKeys/support-bot?$API" \
  --body '{"properties":{"state":"active"}}' --query properties.state -o tsv
```

```powershell title="PowerShell"
'{"properties":{"state":"suspended"}}' | Set-Content keystate.json
az rest --method patch --url "$GW/apiKeys/support-bot?$API" --body "@keystate.json" --query properties.state -o tsv
# Later, to let the key work again:
'{"properties":{"state":"active"}}' | Set-Content keystate.json
az rest --method patch --url "$GW/apiKeys/support-bot?$API" --body "@keystate.json" --query properties.state -o tsv
Remove-Item keystate.json
```

Each command prints the new state, `suspended` or `active`.

<!-- /tracks -->

Then clean up after the leak: remove the value from the notebook and its history, and check
**Monitoring** for calls made with the key.

> [!NOTE]
> If the caller behind a leaked key must keep its identity, for example because a cost-limit override or
> Monitoring history is tied to it, regenerate **both** values instead of deleting the key. Run
> `./infra/rotate-key.sh <key> primary` and then `./infra/rotate-key.sh <key> secondary` (or the PowerShell
> script with `-KeyType`), and give the caller the new value.

## See usage and cost per key

Each key is a caller identity, so Monitoring can break usage down by key. This needs the monitoring setup from
[Monitor usage, cost, and traces](../13-monitoring/README.md) and a few requests with each key.

1. Select **Monitoring** › **Models**.
2. **Active caller identities** counts the API keys and Microsoft Entra identities with observed activity.
3. **Model usage by caller identity** compares caller identities by estimated model cost, tokens, and calls.
4. Use the **All caller identities** filter to scope the page to one key, for example `support-bot`. Keys appear
   by name, marked **API key**.

The same identity drives enforcement. A **Cost limit** counted by **Caller identity** gives each key its own
budget:

![A Cost limit policy with a $100 monthly budget counted by caller identity](../assets/screens/policy-cost-limit-details.png "A Cost limit counted by caller identity: each API key gets its own $100 monthly budget, and a caller that reaches it gets 403 LlmCostQuotaExceeded.")

To set budgets and limits per key, continue with
[Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md).

## When to move to Microsoft Entra ID

API keys are the fastest way to start, but the docs don't recommend them for production.

| | Runtime API key | Microsoft Entra ID with Azure RBAC |
|---|---|---|
| What the gateway sees | One named key | A user, agent, or workload identity in your tenant |
| What it can call | Every published model and MCP server | What its role grants: **AI Gateway User** (models and tools), **AI Gateway Models User**, or **AI Gateway Tools User**, at gateway, alias, or MCP server scope |
| Secret to protect | The key value | None with a managed identity; tokens are short-lived |
| Rotation | You rotate and redistribute values | Microsoft Entra ID issues new tokens |
| Good fit | Prototypes, labs, and tools that only accept a key | Production apps, agents, and per-user access |

Move to Microsoft Entra ID with
[Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md).

## Verify

Run the checks from the lab folder. Only current values should get through; the rotated value, the deleted key,
and a request without a key should all get `401`.

<!-- steps -->

### Load the app-dev key

If `AI_GATEWAY_API_KEY` no longer holds the `app-dev` value, load it again from Key Vault, with
`listSecrets`, or by pasting it, as in [Create a key for each app](#create-a-key-for-each-app).

### Run the checks

```bash title="Bash"
./infra/check-key.sh app-dev
AI_GATEWAY_API_KEY="$OLD_SUPPORT_BOT" ./infra/check-key.sh "rotated value"
AI_GATEWAY_API_KEY="$LEAKED_KEY" ./infra/check-key.sh "deleted key"
./infra/check-key.sh --no-key
```

```powershell title="PowerShell"
./infra/check-key.ps1 -Label app-dev
./infra/check-key.ps1 -ApiKey $OLD_SUPPORT_BOT -Label "rotated value"
./infra/check-key.ps1 -ApiKey $LEAKED_KEY -Label "deleted key"
./infra/check-key.ps1 -NoKey
```

Expected output (your key endings differ):

```text
app-dev        ...Q7xk  HTTP 200  accepted
rotated value  ...m2Rd  HTTP 401  rejected: the key is missing, invalid, rotated, suspended, or deleted
deleted key    ...Vt9a  HTTP 401  rejected: the key is missing, invalid, rotated, suspended, or deleted
no key         -        HTTP 401  rejected: the key is missing, invalid, rotated, suspended, or deleted
```

### Check that the rotated key still works

Load a current `support-bot` value from **View keys**, Key Vault, or `listSecrets`, and run the check again.
After the CLI flow, both the new primary and the new secondary value work. The check prints `HTTP 200`:

```bash title="Bash"
read -rsp "Current support-bot value: " SUPPORT_BOT && echo
AI_GATEWAY_API_KEY="$SUPPORT_BOT" ./infra/check-key.sh support-bot
```

```powershell title="PowerShell"
$SUPPORT_BOT = Read-Host "Current support-bot value" -MaskInput
./infra/check-key.ps1 -ApiKey $SUPPORT_BOT -Label support-bot
```

<!-- /steps -->

## Go further

- **Prompt for the key in MCP clients.** VS Code can ask for the key when it starts an MCP server instead of
  storing it in `mcp.json`. See [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md).
- **Get a rotation reminder.** Set an expiry date on the Key Vault secret with
  `az keyvault secret set-attributes --expires`, and subscribe to the vault's `SecretNearExpiry` event.
- **Automate rotation.** Run the rotation script from a scheduled pipeline that signs in with a workload
  identity, with a pause between the secondary and primary steps for clients to reload.
- **Limit each key.** Give every key its own token allowance with
  [Throttle tokens per caller with token limits](../06-token-limits/README.md).

## Clean up

Keep `app-dev` and `support-bot`:
[Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md) gives them different budgets.
Delete any other keys you created for testing, such as `support-bot-v2`, in **Access** › **Keys** (check box,
then **Delete**), or with the CLI:

```bash
az rest --method delete --url "$GW/apiKeys/support-bot-v2?$API"
```

If you created a Key Vault only for this lab, delete it. Key Vault keeps deleted vaults for a retention period
and reserves the name; purge it if you want to reuse the name right away:

```bash
az keyvault delete -n "$KEY_VAULT"
az keyvault purge -n "$KEY_VAULT"
```

Clear the key values from your shell with `unset AI_GATEWAY_API_KEY OLD_SUPPORT_BOT LEAKED_KEY SUPPORT_BOT`
(Bash) or `Remove-Variable OLD_SUPPORT_BOT, LEAKED_KEY, SUPPORT_BOT; Remove-Item Env:AI_GATEWAY_API_KEY`
(PowerShell). Delete the gateway only when you finish all labs, as described in
[Provision your AI Gateway](../01-provision-gateway/README.md#clean-up).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| A new key gets `401` | The value has a space or line break, or an MCP client sends it in `Authorization` instead of `api-key` | Copy the value again and send it as `api-key: <value>`. |
| `400` with `Specify either an API key or an Authorization header, not both` | The client sends an `api-key` header and an `Authorization` header | Send one of them. With an OpenAI SDK, pass the key as the SDK's API key and remove the extra header. |
| `401` right after **Rotate key** in the portal | Portal rotation replaces the primary value immediately | Give the client the value from **API key rotated successfully**. Next time, use the CLI secondary-value flow. |
| "The key was created, but its value couldn't be retrieved." | You don't have `Microsoft.ApiManagement/aigateways/apiKeys/listSecrets/action` | Use **Rotate key** to get a new value, or ask someone with that permission, such as a Contributor, to read it. |
| `check-key` prints `not checked` with `HTTP 404` | The gateway doesn't know the alias in `AI_GATEWAY_MODEL`, so it never checked the key | Set `AI_GATEWAY_MODEL` to an alias from **Models**, for example the one from lab 02. |
| A key that worked gets `401`, and nobody rotated it | The key is `suspended` | Check `state` with the list command, and set it back to `active` if the suspension is over. |
| `check-key` prints `key accepted, but the call failed` | The key works, but `AI_GATEWAY_MODEL` isn't an alias you can call, or a policy blocked the request | Set `AI_GATEWAY_MODEL` to an alias from **Models**, for example the one from lab 02. |
| `Forbidden` from `az keyvault secret set` or `secret show` | You have no data-plane role on the vault, or the role assignment hasn't applied yet | Assign **Key Vault Secrets Officer** on the vault and wait a few minutes. |
| Monitoring shows no caller identities | Monitoring isn't configured, or the time range has no traffic | Complete [Monitor usage, cost, and traces](../13-monitoring/README.md), send requests with each key, and widen the time range. |

## Next steps

- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): replace keys with identities and
  roles.
- [Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md): give `app-dev` and
  `support-bot` different budgets.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): see usage and cost for each key.
- Docs: [Security and identity in AI Gateway](https://ai.gateway.azure.com/docs/security-identity).
