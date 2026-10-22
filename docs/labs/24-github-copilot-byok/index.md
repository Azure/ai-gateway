---
title: Use your gateway's models in GitHub Copilot
summary: Point GitHub Copilot in VS Code, the Copilot CLI, the Copilot SDK, and the GitHub Copilot app at gpt-6-astra published by your gateway, so every coding agent request uses your key, your token limits, and your monitoring.
category: agents
level: Intermediate
duration: 25
tracks: [portal, cli, iac, code]
order: 17.5
status: new
illustration: diagrams/github-copilot-byok.svg
tags: [GitHub Copilot, BYOK, bring your own key, VS Code, Copilot CLI, Copilot SDK, GitHub Copilot app, gpt-6-astra, Responses API, coding agents]
objectives:
  - Publish gpt-6-astra through the gateway with a per-caller token limit and a runtime key for GitHub Copilot
  - Add the gateway as a custom endpoint in VS Code and run agent mode on gpt-6-astra
  - Run the Copilot CLI against the gateway with provider environment variables
  - Start a Copilot SDK session in Python or TypeScript that sends every model call to the gateway
  - Add the gateway as a model provider in the GitHub Copilot app
  - Track Copilot usage by key in Monitoring and cut off access by suspending the key
prereqs:
  - 02-first-model-call
---

# Use your gateway's models in GitHub Copilot

GitHub Copilot can run on a model that you bring yourself: give it an OpenAI-compatible endpoint and a key, and it
sends every chat and agent request there. Make that endpoint your gateway, and Copilot's traffic gets the same
controls as your apps: a key that you can suspend, a token limit for each caller, and usage in Monitoring. Copilot
never sees a Foundry credential, because the gateway calls Foundry with its managed identity. In this lab you publish
`gpt-6-astra` for Copilot, then connect four Copilot surfaces to it: VS Code, the Copilot CLI, the Copilot SDK, and
the GitHub Copilot app.

![Four GitHub Copilot surfaces send requests with one runtime key to the gpt-6-astra alias on the gateway, which applies a token limit, records usage by key, and calls the Foundry deployment with its managed identity](../assets/diagrams/github-copilot-byok.svg "Every Copilot surface uses the same four settings: the gateway's base URL, the gpt-6-astra alias, the Responses API, and a runtime key. The gateway limits and records the traffic, then calls Foundry with its managed identity.")

## Before you begin

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need a gateway
  with a Foundry provider, and permission to change it, for example **Contributor** on the resource group.
- Quota for `gpt-6-astra` (version `2026-09-03`) in the Foundry account behind your gateway. This lab deploys it
  with 100,000 tokens per minute (TPM), because coding agents send large prompts. Model inference is billed per use.
- For the CLI and IaC tracks: the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later,
  signed in with `az login`, plus `jq` for the Bash snippets.
- At least one Copilot surface. You don't need all four:

  | Surface | Version tested | Needs |
  |---|---|---|
  | [VS Code](https://code.visualstudio.com/download) with GitHub Copilot | 1.143 | Nothing else. Chat and agent mode work with your own model without a GitHub sign-in. |
  | [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) | 1.0.103 | Nothing else. A GitHub sign-in is optional with your own model. |
  | [GitHub Copilot SDK](https://github.com/github/copilot-sdk) | 1.0.26 (TypeScript), 1.0.22 (Python) | Node.js 22.18 or later, or Python 3.11 or later, and a clone of this repository. |
  | [GitHub Copilot app](https://docs.github.com/en/copilot/get-started/quickstart-copilot-app) | Public preview | A GitHub sign-in. A Copilot plan isn't required for your own models. |

> [!IMPORTANT]
> On Copilot Business or Copilot Enterprise, an administrator must allow custom models before VS Code and the
> Copilot app offer them. See
> [Enable custom models for your enterprise](https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-enterprise/enable-custom-models).

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export FOUNDRY_RG="<foundry-resource-group>"      # resource group of the Foundry account behind the gateway
export FOUNDRY_ACCOUNT="<foundry-account-name>"   # the account name, not a project or deployment name
export PROVIDER="foundry-models"                  # the gateway's Foundry provider from lab 02
export MODEL="gpt-6-astra"                        # the deployment, the backend model, and the alias
export KEY_NAME="github-copilot"                  # the runtime key that Copilot uses

export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(az resource show -g "$RG" -n "$GATEWAY" --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv)"
export GW="https://management.azure.com$GATEWAY_ID"
export WS="$GW/workspaces/default"
export AI_GATEWAY_URL="https://$(az resource show --ids "$GATEWAY_ID" --query properties.frontend.defaultHostname -o tsv)"
export AI_GATEWAY_MODEL="$MODEL"
```

```powershell title="PowerShell"
$RG              = "<resource-group>"
$GATEWAY         = "<gateway>"
$FOUNDRY_RG      = "<foundry-resource-group>"     # resource group of the Foundry account behind the gateway
$FOUNDRY_ACCOUNT = "<foundry-account-name>"       # the account name, not a project or deployment name
$PROVIDER        = "foundry-models"               # the gateway's Foundry provider from lab 02
$MODEL           = "gpt-6-astra"                  # the deployment, the backend model, and the alias
$KEY_NAME        = "github-copilot"               # the runtime key that Copilot uses

$API        = "api-version=2025-09-01-preview"
$GATEWAY_ID = az resource show -g $RG -n $GATEWAY --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv
$GW         = "https://management.azure.com$GATEWAY_ID"
$WS         = "$GW/workspaces/default"
$env:AI_GATEWAY_URL   = "https://$(az resource show --ids $GATEWAY_ID --query properties.frontend.defaultHostname -o tsv)"
$env:AI_GATEWAY_MODEL = $MODEL
```

> [!TIP]
> If you imported models in the portal in lab 02, your provider has another name. List the providers with
> `az rest --url "$WS/modelProviders?$API" --query "value[].name" -o tsv` and set `PROVIDER` to the one for your
> Foundry account.

Then create a small practice project with two deliberate problems: `add` subtracts, and `divide` doesn't guard against
zero. The VS Code and CLI sections ask Copilot to work on it. Create it outside any repository:

```bash title="Bash"
mkdir -p ~/contoso-calc
cat > ~/contoso-calc/calc.py <<'EOF'
"""Tiny calculator used to try GitHub Copilot with a model from Azure AI Gateway."""


def add(a: float, b: float) -> float:
    return a - b


def divide(a: float, b: float) -> float:
    return a / b


if __name__ == "__main__":
    print(add(2, 3), divide(10, 2))
EOF
```

```powershell title="PowerShell"
New-Item -ItemType Directory -Force -Path ~/contoso-calc | Out-Null
@'
"""Tiny calculator used to try GitHub Copilot with a model from Azure AI Gateway."""


def add(a: float, b: float) -> float:
    return a - b


def divide(a: float, b: float) -> float:
    return a / b


if __name__ == "__main__":
    print(add(2, 3), divide(10, 2))
'@ | Set-Content -Path ~/contoso-calc/calc.py
```

## How it works

Bring your own key (BYOK) replaces the model endpoint behind Copilot. Copilot still runs its agent loop on your
machine: it reads files, plans, calls tools, and asks before it edits or runs commands. Each model request goes to the
gateway instead of GitHub's model service. Every surface needs the same four settings:

| Setting | Value | Why |
|---|---|---|
| Base URL | `https://<gateway-host>/default/models/openai/v1` | The gateway's OpenAI-compatible endpoint. VS Code wants the full URL, with `/responses` at the end. |
| Model | `gpt-6-astra` | The alias. Copilot sends it in the request's `model` field, and the gateway routes by alias. When the alias has the model's well-known name, Copilot also applies the prompts and token sizes it uses for that model. |
| API | Responses | Copilot recommends the Responses API for GPT-5 and later models. The gateway serves both `/responses` and `/chat/completions` for this model. |
| API key | The `github-copilot` runtime key | Copilot sends it as `Authorization: Bearer`. The gateway also accepts an `api-key` header, but not both in one request. |

Two things differ from an app that calls the gateway:

- **You add the model by hand.** Clients often call `GET /models` to discover what an endpoint offers, but the
  gateway doesn't serve a model list. Each surface lets you type the model name instead.
- **Agents send big requests.** Every request carries Copilot's system prompt, its tool definitions, and the
  conversation so far. In testing, a one-line question from the Copilot CLI used 14,000 to 38,000 input tokens.
  That's why this lab gives each caller 100,000 tokens per minute, and why one key per tool or per developer makes
  usage easy to read.

## Publish gpt-6-astra for Copilot

Deploy `gpt-6-astra` in Foundry, publish it through the gateway under the alias `gpt-6-astra` with a token limit of
100,000 tokens per minute for each caller, and create the runtime key `github-copilot`. Pick a track.

<!-- track: portal | Portal -->

### Deploy the model in Foundry

In the [Foundry portal](https://ai.azure.com), open the Foundry account behind your gateway and deploy `gpt-6-astra`
with the deployment name `gpt-6-astra`. Or paste the command from the **Azure CLI** track's first step into
[Azure Cloud Shell](https://shell.azure.com).

### Import the deployment

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top bar.
2. Select **Models** › **Add** › **Models from Microsoft Foundry**.
3. Select the subscription and resource group of your Foundry account, then select the `gpt-6-astra` deployment.
   Keep **Managed identity** as the **Authentication method**.
4. Under **Aliases**, keep **Create an alias for each model** selected, then select **Add models**.

### Publish the gpt-6-astra alias

The import names its alias after the provider and the deployment, for example `<foundry-account-name>/gpt-6-astra`.
Copilot needs the plain model name, so add an alias called `gpt-6-astra`:

1. Select **Models** › **Aliases** › **Add alias**.
2. On **Basics**, set **Alias name** to `gpt-6-astra`. Select **Next**.
3. On **Select models**, select `gpt-6-astra` in **Available backend models**. Select **Next**.
4. Keep the defaults on **Priority and weights**, select **Next**, then select **Create** on **Review**.

### Add the token limit

1. Select **Policies** › **Add policy**. On the **Type** step, under **Cost & Rate Limits**, select
   **Token rate limit**, then **Next**.
2. On the **Scope** step, select **Individual assets**, select the `gpt-6-astra` alias, then **Next**.
3. On the **Details** step, set **Time period** to **Per minute**, **Allowed tokens** to `100000`, and
   **Counter dimensions** to **Caller identity**. Select **Create**.

### Create the key for Copilot

1. Select **Access** › **Keys** › **Create API key**.
2. In **Key name**, enter `github-copilot` and select **Create**.
3. Copy the value from **API key created successfully**, for example with **Copy & done**, and paste it into your
   shell without echoing it:

```bash title="Bash"
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

> **Checkpoint**
> **Models** › **Aliases** lists `gpt-6-astra`, **Policies** lists a **Token rate limit** of 100,000 tokens per
> minute scoped to it, and **Access** › **Keys** lists `github-copilot`.

<!-- track: cli | Azure CLI -->

### Deploy the model in Foundry

If the command fails with `InsufficientQuota`, use `--sku-name DataZoneStandard`, or deploy in another region.

```bash title="Bash"
export FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
az cognitiveservices account deployment create -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" \
  --deployment-name "$MODEL" --model-name "$MODEL" --model-version 2026-09-03 \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100 \
  --query "{name:name, state:properties.provisioningState}"
```

```powershell title="PowerShell"
$FOUNDRY_ID = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
az cognitiveservices account deployment create -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT `
  --deployment-name $MODEL --model-name $MODEL --model-version 2026-09-03 `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100 `
  --query "{name:name, state:properties.provisioningState}"
```

### Register the model with its token limit

A backend model carries its own `policies` array, so one `PUT` registers the deployment and its limit.

```bash title="Bash"
az rest --method put --url "$WS/modelProviders/$PROVIDER/models/$MODEL?$API" \
  --body "$(jq -cn --arg id "$FOUNDRY_ID/deployments/$MODEL" --arg m "$MODEL" '{properties: {
      displayName: $m, apiFormat: "OpenAIChatCompletions",
      supportedEndpoints: ["/openai/v1/chat/completions", "/openai/v1/responses"],
      deployment: {resourceId: $id, modelName: $m, modelVersion: "2026-09-03"},
      policies: [{type: "tokenLimit", period: "minute", count: 100000, counterKey: ["identity"]}]}}')" \
  --query "{name:name, policies:properties.policies}"
```

```powershell title="PowerShell"
@{ properties = @{
    displayName        = $MODEL
    apiFormat          = "OpenAIChatCompletions"
    supportedEndpoints = @("/openai/v1/chat/completions", "/openai/v1/responses")
    deployment         = @{ resourceId = "$FOUNDRY_ID/deployments/$MODEL"; modelName = $MODEL; modelVersion = "2026-09-03" }
    policies           = @(@{ type = "tokenLimit"; period = "minute"; count = 100000; counterKey = @("identity") })
  } } | ConvertTo-Json -Depth 10 -Compress | Set-Content body.json
az rest --method put --url "$WS/modelProviders/$PROVIDER/models/$MODEL`?$API" --body "@body.json" `
  --query "{name:name, policies:properties.policies}"
```

### Publish the gpt-6-astra alias

```bash title="Bash"
az rest --method put --url "$WS/aliases/$MODEL?$API" \
  --body "$(jq -cn --arg id "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$MODEL" \
      '{properties: {backendModels: [{resourceId: $id}]}}')" \
  --query "{alias:properties.aliasName, target:properties.backendModels[0].resourceId}"
```

```powershell title="PowerShell"
@{ properties = @{ backendModels = @(@{ resourceId = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$MODEL" }) } } |
  ConvertTo-Json -Depth 10 -Compress | Set-Content body.json
az rest --method put --url "$WS/aliases/$MODEL`?$API" --body "@body.json" `
  --query "{alias:properties.aliasName, target:properties.backendModels[0].resourceId}"
Remove-Item body.json
```

### Create the key for Copilot

The `PUT` returns metadata only. Read the value with `listSecrets` straight into a variable, so it never appears on
screen.

```bash title="Bash"
az rest --method put --url "$GW/apiKeys/$KEY_NAME?$API" \
  --body '{"properties":{"displayName":"GitHub Copilot"}}' --query "{name:name, state:properties.state}"

AI_GATEWAY_API_KEY="$(az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" \
  --query primaryKey -o tsv)" && export AI_GATEWAY_API_KEY
```

```powershell title="PowerShell"
'{"properties":{"displayName":"GitHub Copilot"}}' | Set-Content body.json
az rest --method put --url "$GW/apiKeys/$KEY_NAME`?$API" --body "@body.json" `
  --query "{name:name, state:properties.state}"
Remove-Item body.json

$env:AI_GATEWAY_API_KEY = az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" `
  --query primaryKey -o tsv
```

> **Checkpoint**
> The model output shows one policy with `"type": "tokenLimit"` and `"count": 100000`, the alias output shows your
> model's ID as `target`, and the key output shows `github-copilot` as `active`.

<!-- track: iac | Bicep -->

### Review the template

The template deploys `gpt-6-astra` in your Foundry account, then reuses lab 02's template to register it under your
provider, publish the `gpt-6-astra` alias with the token limit, and create the `github-copilot` key.

<!-- include: infra/main.bicep -->

On GitHub, open [infra/main.bicep](infra/main.bicep) and [infra/deployment.bicep](infra/deployment.bicep).

### Deploy the template

Run the deployment from the lab folder (`labs/24-github-copilot-byok`). If the Foundry deployment fails with
`InsufficientQuota`, add `skuName=DataZoneStandard` to the parameters.

```bash title="Bash"
FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"

az deployment group create -g "$RG" -n 24-github-copilot \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" foundryAccountId="$FOUNDRY_ID" providerName="$PROVIDER" \
  --query properties.outputs
```

```powershell title="PowerShell"
$FOUNDRY_ID = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv

az deployment group create -g $RG -n 24-github-copilot `
  --template-file infra/main.bicep `
  --parameters gatewayName=$GATEWAY foundryAccountId=$FOUNDRY_ID providerName=$PROVIDER `
  --query properties.outputs
```

The outputs show `aliasName` (`gpt-6-astra`), `apiKeyName` (`github-copilot`), and `modelEndpoint`, the base URL
that Copilot needs.

### Read the key

Template outputs never contain the key value. Read it with `listSecrets` straight into a variable.

```bash title="Bash"
AI_GATEWAY_API_KEY="$(az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" \
  --query primaryKey -o tsv)" && export AI_GATEWAY_API_KEY
```

```powershell title="PowerShell"
$env:AI_GATEWAY_API_KEY = az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" `
  --query primaryKey -o tsv
```

> **Checkpoint**
> The deployment succeeds, and **Models** › **Aliases** in the portal lists `gpt-6-astra`.

<!-- /tracks -->

### Test the endpoint

Before you configure Copilot, call the alias the way Copilot does: the Responses API with a bearer token.

```bash title="Bash"
curl -sS "${AI_GATEWAY_URL%/}/default/models/openai/v1/responses" \
  -H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"input\":\"In one sentence, what is a code review for?\"}" \
  | jq -r '"model: \(.model)", ([.output[] | select(.type == "message") | .content[] | select(.type == "output_text") | .text] | join(""))'
```

```powershell title="PowerShell"
$body = @{ model = $env:AI_GATEWAY_MODEL; input = "In one sentence, what is a code review for?" } | ConvertTo-Json

$reply = Invoke-RestMethod -Method Post `
  -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/responses" `
  -Headers @{ Authorization = "Bearer $env:AI_GATEWAY_API_KEY" } -ContentType "application/json" -Body $body
"model: $($reply.model)"
($reply.output | Where-Object type -eq "message").content.text -join ""
```

Expected output (your text differs):

```text
model: gpt-6-astra
A code review checks changes for bugs, clarity, and consistency before they're merged.
```

> [!NOTE]
> A new alias, policy, or key can take a minute to apply. If the call returns `401` or `404`, wait a minute and try
> again.

## Connect VS Code

VS Code adds your own models through a **Custom Endpoint** model group. It stores the key in its secret storage and
the rest in `chatLanguageModels.json`.

<!-- steps -->

### Add the gateway as a custom endpoint

1. Open the practice project in VS Code, for example with `code ~/contoso-calc`.
2. Open the Command Palette (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>, or <kbd>Cmd</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>
   on macOS) and run **Chat: Manage Language Models**. The **Language Models** editor opens.

   ![The Language Models editor with the Add Models and Install Model Providers buttons](../assets/screens/copilot-vscode-01-language-models.webp "Chat: Manage Language Models opens the Language Models editor. Add Models starts the custom endpoint setup.")

3. Select **Add Models** › **Custom Endpoint**, and enter `AI Gateway` as the group name.
4. Paste your `github-copilot` key into **AI Gateway: API Key** and press <kbd>Enter</kbd>. To copy it from the shell
   without printing it, run `printf %s "$AI_GATEWAY_API_KEY" | pbcopy` on macOS, or
   `Set-Clipboard $env:AI_GATEWAY_API_KEY` in PowerShell.

   ![The AI Gateway: API Key prompt with a masked value](../assets/screens/copilot-vscode-02-api-key.webp "VS Code masks the key and keeps it in its secret storage, not in a settings file.")

5. In **AI Gateway: API Type**, select **Responses**.

   ![The AI Gateway: API Type picker with Chat Completions, Responses, and Messages](../assets/screens/copilot-vscode-03-api-type.webp "Pick Responses. It becomes the default for every model in the group.")

### Add gpt-6-astra to the group

VS Code opens `chatLanguageModels.json` with the new group. The gateway has no model list to discover, so add the
model to `models` yourself. Print the URL to paste:

```bash
echo "${AI_GATEWAY_URL%/}/default/models/openai/v1/responses"
```

Then make the group look like this. Keep the `apiKey` value that VS Code wrote: it points at the secret, not the key
itself.

```jsonc title="chatLanguageModels.json"
[
  {
    "name": "AI Gateway",
    "vendor": "customendpoint",
    "apiKey": "${input:chat.lm.secret.<id>}",
    "apiType": "responses",
    "models": [
      {
        "id": "gpt-6-astra",
        "name": "GPT-6 Astra (AI Gateway)",
        "url": "https://<gateway-host>/default/models/openai/v1/responses",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 128000,
        "maxOutputTokens": 16000
      }
    ]
  }
]
```

![chatLanguageModels.json with the AI Gateway group and the gpt-6-astra model](../assets/screens/copilot-vscode-04-config.webp "The id is the alias that VS Code sends as the model. The name is what the model picker shows.")

| Field | What it does |
|---|---|
| `id` | The alias, sent as `model` in each request. |
| `name` | The label in the model picker. Copilot already offers a built-in **GPT-6 Astra**, so a distinct name tells them apart. |
| `url` | The full Responses URL on your gateway. |
| `toolCalling` | Tells VS Code that the model can call tools, which agent mode needs. |
| `maxInputTokens`, `maxOutputTokens` | How much context VS Code sends and how long a reply it asks for. |

Save the file.

### Pick the model and run an agent task

1. Open the Chat view (<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>I</kbd>, or <kbd>Ctrl</kbd>+<kbd>Cmd</kbd>+<kbd>I</kbd> on
   macOS) and select **Agent**.
2. Open the model picker, select the **AI Gateway** tab, and select **GPT-6 Astra (AI Gateway)**. If the model isn't
   listed, run **Developer: Reload Window**.

   ![The model picker with the AI Gateway tab and GPT-6 Astra (AI Gateway)](../assets/screens/copilot-vscode-05-model-picker.webp "Models from the custom endpoint get their own tab in the model picker.")

3. Send this prompt:

   ```text
   Fix the bug in calc.py and add a guard for division by zero
   ```

Copilot reads the file, changes `add` to return `a + b`, makes `divide` raise `ZeroDivisionError` when `b` is zero,
and checks its work. Review the diff and select **Keep**.

![VS Code agent mode fixed add and added a zero guard to divide, with GPT-6 Astra (AI Gateway) selected](../assets/screens/copilot-vscode-06-agent.webp "Agent mode on gpt-6-astra through the gateway: the diff in the editor, the summary in chat, and Keep or Undo for the change.")

<!-- /steps -->

> **Checkpoint**
> The chat input shows **GPT-6 Astra (AI Gateway)**, and `calc.py` now adds correctly and refuses to divide by zero.

> [!TIP]
> Without a GitHub sign-in, VS Code asks you to pick utility models for chat titles, commit messages, and pull
> request descriptions. Set `chat.utilityModel` and `chat.utilitySmallModel` to your gateway model. Inline
> suggestions still need a GitHub sign-in.

## Connect the Copilot CLI

The Copilot CLI reads its provider from environment variables, so you can switch between the gateway and GitHub's
models per terminal.

<!-- steps -->

### Point the CLI at the gateway

| Variable | Value |
|---|---|
| `COPILOT_PROVIDER_BASE_URL` | `https://<gateway-host>/default/models/openai/v1`. Setting it turns on BYOK. |
| `COPILOT_PROVIDER_WIRE_API` | `responses`. The default is `completions`. |
| `COPILOT_PROVIDER_API_KEY` | Your `github-copilot` key, sent as a bearer token. |
| `COPILOT_MODEL` | `gpt-6-astra`, the alias. |
| `COPILOT_OFFLINE` | Optional. `true` also turns off the GitHub sign-in, telemetry, web tools, and the GitHub MCP server. |

```bash title="Bash"
export COPILOT_PROVIDER_BASE_URL="${AI_GATEWAY_URL%/}/default/models/openai/v1"
export COPILOT_PROVIDER_WIRE_API="responses"
export COPILOT_PROVIDER_API_KEY="$AI_GATEWAY_API_KEY"
export COPILOT_MODEL="$AI_GATEWAY_MODEL"
```

```powershell title="PowerShell"
$env:COPILOT_PROVIDER_BASE_URL = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1"
$env:COPILOT_PROVIDER_WIRE_API = "responses"
$env:COPILOT_PROVIDER_API_KEY  = $env:AI_GATEWAY_API_KEY
$env:COPILOT_MODEL             = $env:AI_GATEWAY_MODEL
```

These variables last for the current terminal. Run `copilot help environment` for the full list.

### Ask a quick question

`copilot -p` runs one prompt and exits:

```bash
cd ~/contoso-calc
copilot -p "Which model are you? Answer in one short sentence."
```

Expected output (your numbers differ):

```text
I'm powered by gpt-6-astra (model ID: gpt-6-astra).

Changes    +0 -0
Duration   6s
Tokens     ↑ 14.4k (14.4k written) • ↓ 24
```

The **Tokens** line shows how much context even a short question carries.

### Run an agent task

Start an interactive session in the project, and select **Yes** when the CLI asks whether you trust the folder:

```bash
copilot
```

Send this prompt:

```text
Add a multiply function to calc.py and unittest tests in test_calc.py, then run them
```

Copilot plans the change and asks before it edits a file or runs a command. Select **Yes** to approve each step, or
**Yes, and don't ask again** to approve that kind of step for this folder.

![The Copilot CLI asks to update calc.py with a new multiply function](../assets/screens/copilot-cli-01-approve.webp "Before each edit, the CLI shows the diff and asks for approval.")

![The Copilot CLI added multiply, created test_calc.py, and ran the tests: all 4 tests passed, with gpt-6-astra in the status bar](../assets/screens/copilot-cli-02-done.webp "The task is done: the CLI added multiply, wrote the tests, and ran them. The status bar shows gpt-6-astra.")

<!-- /steps -->

> **Checkpoint**
> The status bar shows `gpt-6-astra`, and the tests pass. If you skipped the VS Code section, Copilot may also fix
> `add` when the first test run fails. Type `/exit` to leave the session.

## Connect the Copilot SDK

The [GitHub Copilot SDK](https://github.com/github/copilot-sdk) runs the same agent as the CLI inside your own app.
Pass a `provider` when you create a session, and the session sends its model calls to the gateway. The SDK packages
bring the Copilot runtime with them, so you don't need to install the CLI. No GitHub sign-in is needed.

<!-- steps -->

### Review the samples

The samples read `AI_GATEWAY_URL`, `AI_GATEWAY_API_KEY`, and, optionally, `AI_GATEWAY_MODEL` from the environment,
then ask the agent which model it is and to list the files in the current folder. `approveAll` lets the agent run
tools without asking, which suits a sample. In an app, decide which tools to allow in `onPermissionRequest`.

<!-- include: infra/copilot-sdk.ts -->

<!-- include: infra/copilot_sdk.py -->

### Run a sample

Run the commands from the lab folder (`labs/24-github-copilot-byok`).

```bash title="TypeScript"
cd infra
npm install          # @github/copilot-sdk
npm start            # runs copilot-sdk.ts on Node.js 22.18 or later
```

```bash title="Python"
cd infra
pip install -r requirements.txt     # github-copilot-sdk
python copilot_sdk.py
```

Expected output (your text differs):

```text
I'm powered by gpt-6-astra (model ID: gpt-6-astra).

Files in this folder:
- copilot-sdk.ts
- copilot_sdk.py
- deployment.bicep
- main.bicep
- package.json
- requirements.txt
```

The samples print the agent's last message. If the agent answers in two messages, you see only the file list.

![VS Code with copilot-sdk.ts open and npm start printing that the agent runs on gpt-6-astra and listing the folder](../assets/screens/copilot-sdk-01-run.webp "The SDK session runs on gpt-6-astra through the gateway, and its tools work as in the CLI.")

To send your own prompt, pass it as an argument, for example `npm start -- "Summarize package.json"` or
`python copilot_sdk.py "Summarize requirements.txt"`.

<!-- /steps -->

> **Checkpoint**
> The sample names `gpt-6-astra` and lists the folder's files.

## Connect the GitHub Copilot app

The [GitHub Copilot app](https://docs.github.com/en/copilot/get-started/quickstart-copilot-app) is a desktop app for
running Copilot agent sessions across your projects. It adds your own models as **model providers** and keeps their
keys in the system credential store.

> [!NOTE]
> The GitHub Copilot app is in public preview, and its screens change often. These steps follow
> [Use BYOK models in the GitHub Copilot app](https://docs.github.com/en/copilot/how-tos/github-copilot-app/use-byok-models).
> The picture below is an illustration, not a screenshot, so labels in your version can differ.

![An illustration of the four steps and the Add provider form, with the gateway's base URL, the API key, the Responses wire API, and the gpt-6-astra model](../assets/diagrams/copilot-app-provider.svg "Add the gateway once as an OpenAI-compatible provider. Its models then appear in the app's model picker.")

<!-- steps -->

### Add the gateway as a model provider

1. Open the GitHub Copilot app and sign in with your GitHub account.
2. Open the app settings and select **Model providers** › **Add provider**.
3. Select **Any OpenAI-compatible HTTP endpoint**. Don't pick **Azure OpenAI** or **Microsoft Foundry**: they expect
   those services' own URLs and keys.
4. Enter the provider details:

   | Field | Value |
   |---|---|
   | Display name | `AI Gateway` |
   | Base URL | `https://<gateway-host>/default/models/openai/v1` |
   | API key | Your `github-copilot` key |
   | Wire API, if shown | Responses |

5. The gateway doesn't serve a `/models` list, so the app can't discover its models. Add the model by hand with the
   model ID `gpt-6-astra`.
6. Select **Add provider**.

### Start a session on gpt-6-astra

The provider's models appear in the model picker next to GitHub's. Start a session on the `contoso-calc` folder,
select **gpt-6-astra** from the **AI Gateway** provider, and ask a question, for example
`Which model are you, and what does calc.py do?`.

<!-- /steps -->

> **Checkpoint**
> The reply names `gpt-6-astra`, and the request shows up in the gateway's Monitoring under the `github-copilot` key.

## Verify

Every surface you connected sends its requests with the `github-copilot` key. Use it to see the traffic and to switch
Copilot off.

<!-- steps -->

### See Copilot's usage by key

If you set up Monitoring in [Monitor usage, cost, and traces](../13-monitoring/README.md), open **Monitoring** ›
**Models** in the AI Gateway portal. `gpt-6-astra` lists the calls and the input and output tokens from your Copilot
sessions, and **Model usage by caller identity** shows them under the `github-copilot` key. The input tokens are far
higher than the output tokens: that's the context that the agent sends with every request.

### Cut Copilot off by suspending the key

Suspend the key, then run the CLI again. The settings are unchanged, but the gateway now rejects the key:

```bash title="Bash"
az rest --method patch --url "$GW/apiKeys/$KEY_NAME?$API" \
  --body '{"properties":{"state":"suspended"}}' --query properties.state -o tsv
sleep 30
cd ~/contoso-calc && copilot -p "Say hi"
```

```powershell title="PowerShell"
'{"properties":{"state":"suspended"}}' | Set-Content keystate.json
az rest --method patch --url "$GW/apiKeys/$KEY_NAME`?$API" --body "@keystate.json" --query properties.state -o tsv
Start-Sleep 30
Set-Location ~/contoso-calc; copilot -p "Say hi"
```

Expected output, after the CLI retries twice:

```text
suspended
Request failed due to a transient API error. Retrying...
Request failed due to a transient API error. Retrying...
Authentication failed with provider at https://<gateway-host>/default/models/openai/v1 (HTTP 401).
```

VS Code, the SDK, and the app get the same `401`. One key change cuts off every Copilot surface that uses the key, on
every machine, without touching their settings.

### Turn Copilot back on

```bash title="Bash"
az rest --method patch --url "$GW/apiKeys/$KEY_NAME?$API" \
  --body '{"properties":{"state":"active"}}' --query properties.state -o tsv
sleep 30
copilot -p "Say hi in three words"
```

```powershell title="PowerShell"
'{"properties":{"state":"active"}}' | Set-Content keystate.json
az rest --method patch --url "$GW/apiKeys/$KEY_NAME`?$API" --body "@keystate.json" --query properties.state -o tsv
Remove-Item keystate.json
Start-Sleep 30
copilot -p "Say hi in three words"
```

<!-- /steps -->

> **Checkpoint**
> The CLI failed with `HTTP 401` while the key was suspended, and answered again once it was `active`.

## Go further

- **Sign in with Microsoft Entra ID instead of a key.** If the gateway accepts Entra tokens, as in
  [Authorize callers with Microsoft Entra ID](../11-entra-rbac/README.md), set `COPILOT_PROVIDER_BEARER_TOKEN` for the
  CLI, or pass a bearer token in the SDK's `provider` settings. Tokens expire, so refresh them for long sessions.
- **Fetch the key when it's needed.** `COPILOT_PROVIDER_API_KEY_COMMAND` runs a command for each request and uses its
  output as the key, for example `az keyvault secret show --vault-name <vault> -n github-copilot --query value -o tsv`.
  The key then never sits in your shell profile, and a rotated key takes effect right away.
- **Give each developer or tool its own key.** Keys are cheap, and per-key usage in Monitoring shows who uses how
  much. Rotate or revoke them with [Manage runtime API keys](../10-api-keys/README.md).
- **Route Copilot across models.** Point the `gpt-6-astra` alias at several backend models, as in
  [Route by priority and weight](../22-model-routing/README.md). VS Code chains Responses API turns with
  `previous_response_id` by default; if the backends don't share state, set `"statefulResponses": false` on the model
  in `chatLanguageModels.json`.
- **Offer more models.** Publish more aliases and add each one to `models` in VS Code, or to the provider in the app.
  For the CLI, set `COPILOT_MODEL` to a different alias. If an alias doesn't have a well-known model name, set
  `COPILOT_PROVIDER_MODEL_ID` to the model it serves, so the CLI picks the right prompts and token sizes.

## Clean up

Remove the gateway from each Copilot surface you configured:

- **VS Code:** delete the **AI Gateway** group from `chatLanguageModels.json`, or remove it in the
  **Language Models** editor.
- **Copilot CLI:** close the terminal, or run `unset COPILOT_PROVIDER_BASE_URL COPILOT_PROVIDER_WIRE_API COPILOT_PROVIDER_API_KEY COPILOT_MODEL`
  (Bash) or `Remove-Item Env:COPILOT_PROVIDER_*, Env:COPILOT_MODEL` (PowerShell).
- **GitHub Copilot app:** remove the **AI Gateway** provider in **Model providers**.

Then delete the key. In the portal, delete `github-copilot` in **Access** › **Keys**. From a shell:

```bash title="Bash"
az rest --method delete --url "$GW/apiKeys/$KEY_NAME?$API"
rm -rf ~/contoso-calc
```

```powershell title="PowerShell"
az rest --method delete --url "$GW/apiKeys/$KEY_NAME`?$API"
Remove-Item -Recurse -Force ~/contoso-calc
```

If you don't need `gpt-6-astra` any more, also delete the alias, the backend model, and the Foundry deployment. In
the portal, delete them in **Models** and in Foundry. From a shell:

```bash title="Bash"
az rest --method delete --url "$WS/aliases/$MODEL?$API"
az rest --method delete --url "$WS/modelProviders/$PROVIDER/models/$MODEL?$API"
az cognitiveservices account deployment delete -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --deployment-name "$MODEL"
```

```powershell title="PowerShell"
az rest --method delete --url "$WS/aliases/$MODEL`?$API"
az rest --method delete --url "$WS/modelProviders/$PROVIDER/models/$MODEL`?$API"
az cognitiveservices account deployment delete -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --deployment-name $MODEL
```

If you imported the model in the portal, also delete its `<foundry-account-name>/gpt-6-astra` alias. Keep the gateway
and the provider: the other labs reuse them.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `HTTP 401` or "Authentication failed with provider" | The key is wrong, suspended, or deleted, or the new key isn't active yet | Check the key's state in **Access** › **Keys**, wait a minute after you create it, and paste it again. |
| `400` on every request from a custom client | The request sends both `Authorization` and `api-key` | Send one of them. Copilot sends `Authorization: Bearer` only. |
| `404`, or a "model not found" error | The model name isn't an alias on the gateway, for example the portal import's `<foundry-account-name>/gpt-6-astra` | Publish the `gpt-6-astra` alias, or set the model ID to the alias that exists. |
| The model doesn't appear in VS Code or the app | The gateway has no `/models` list to discover, or VS Code hasn't reloaded the file | Add `gpt-6-astra` by hand, then run **Developer: Reload Window** in VS Code. |
| The model is missing from the picker in Agent mode | `toolCalling` is missing or `false` | Set `"toolCalling": true` on the model. |
| VS Code or the app doesn't offer your own models at all | Your Copilot Business or Enterprise organization hasn't allowed custom models | Ask an administrator to enable them. |
| Replies are empty or cut off, or tool calls fail | The surface uses Chat Completions with a reasoning model | Set the API to Responses: `apiType` in VS Code, `COPILOT_PROVIDER_WIRE_API=responses` for the CLI, `wireApi` in the SDK. |
| `429 Too Many Requests` | Copilot used the key's 100,000 tokens for this minute | Wait for the `Retry-After` interval, or raise the token limit. |
| The CLI's first interactive prompt doesn't respond | A slow first connection | Press <kbd>Ctrl</kbd>+<kbd>C</kbd> and send the prompt again. |
| Two **GPT-6 Astra** entries in VS Code's model picker | Copilot's built-in model and yours share a name | Give yours a distinct `name`, such as `GPT-6 Astra (AI Gateway)`. |

## Next steps

- [Manage runtime API keys](../10-api-keys/README.md): rotate, suspend, and revoke the keys that tools use.
- [Throttle tokens per caller with token limits](../06-token-limits/README.md): tune the limit for agent traffic.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): see Copilot's usage by key next to your apps.
- [Build on your gateway with coding agents](../17-coding-agent-plugin/README.md): let a coding agent write the client
  code for your gateway.
- [Use BYOK models in the GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models),
  [the Copilot SDK](https://github.com/github/copilot-sdk/blob/main/docs/auth/byok.md), and
  [VS Code](https://code.visualstudio.com/docs/copilot/customization/language-models).
