---
title: Screen prompts and responses with content safety
summary: Add a content safety policy that screens prompts, tool inputs, and responses for hate, self-harm, sexual, and violent content, tune each category's threshold, and see how blocked calls return 400.
category: governance
level: Beginner
duration: 20
tracks: [portal, cli, rest]
order: 8
illustration: diagrams/request-lifecycle.svg
tags: [contentSafety, Azure AI Content Safety, responsible AI, severity threshold, "400", content filter]
objectives:
  - Explain how content safety severity thresholds decide what the gateway blocks
  - Add a content safety policy to a model in the portal, with the Azure CLI, or with the REST API
  - Override the threshold for one category without changing the others
  - Test the policy with benign prompts and tell a gateway block from a Foundry content filter result
prereqs:
  - 02-first-model-call
---

# Screen prompts and responses with content safety

Your gateway now serves a customer-facing assistant and several internal agents, on models from more than one
provider. Your responsible AI review asks for one consistent rule: every prompt and every response is screened
for harmful content, whichever model or tool handles it. In this lab you add a **content safety** policy at the
gateway, tune it per category, and see what a blocked call looks like to a client.

![The request lifecycle through authentication, policies, the backend, and telemetry](../assets/diagrams/request-lifecycle.svg "Content safety is one of the policies that the gateway evaluates on every request. When it blocks a call, the client gets 400.")

<!-- widget: request-lifecycle {"focus":"contentSafety"} -->

## Before you begin

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need a
  gateway, an imported model, a callable alias, and a runtime API key from **Access** › **Keys**.
- For the CLI and REST tracks: the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75
  or later, signed in with `az login`, and the `aigateway` extension
  ([install it](https://github.com/Azure/ai-gateway/tree/main/cli#install)). The REST track also uses `jq`.
- For the **Verify** script: `curl` and `jq` (Bash) or PowerShell 7 or later.
- Permission to change the gateway, for example **Contributor** on the resource group.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export PROVIDER="<provider-name>"          # for example foundry-models
export MODEL="<model-name>"                # the backend model name under that provider

export AI_GATEWAY_URL="$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.gatewayUrl -o tsv)"
# For Foundry imports, the default alias matches the deployment's model name.
export AI_GATEWAY_MODEL="$(az aigateway model show -g "$RG" --gateway-name "$GATEWAY" \
  --provider-name "$PROVIDER" -n "$MODEL" --query properties.deployment.modelName -o tsv)"
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG       = "<resource-group>"
$GATEWAY  = "<gateway>"
$PROVIDER = "<provider-name>"              # for example foundry-models
$MODEL    = "<model-name>"                 # the backend model name under that provider

$env:AI_GATEWAY_URL = az aigateway show -g $RG -n $GATEWAY --query properties.gatewayUrl -o tsv
# For Foundry imports, the default alias matches the deployment's model name.
$env:AI_GATEWAY_MODEL = az aigateway model show -g $RG --gateway-name $GATEWAY `
  --provider-name $PROVIDER -n $MODEL --query properties.deployment.modelName -o tsv
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

## How it works

A content safety policy screens prompts, tool inputs, and responses with Azure AI Content Safety. It rates
content in four categories: **Hate**, **Self-harm**, **Sexual**, and **Violence**. You set a severity threshold
for each category independently. When content reaches the threshold, the gateway blocks the call and returns
`400`. A blocked prompt never reaches the backend.

The threshold is the lowest severity that gets blocked, so a **lower** threshold blocks **more**:

| Portal label | CLI and REST value | What it blocks |
|---|---|---|
| **Strict** | `Low` | The most content: low, medium, and high severity |
| **Balanced** (default) | `Medium` | Medium and high severity |
| **Lenient** | `High` | Only the most concerning, high-severity content |
| **Off** | `None` | Nothing in this category |

You can attach content safety to **models** and **MCP servers**. On an MCP server, it screens the tool inputs
that agents send and the results that tools return. Every applicable policy is evaluated, and any one of them
can block the call.

> [!NOTE]
> Foundry deployments have their own **Content filter**, shown on the model's details page in **Models**. That
> filter runs inside Foundry, for that one deployment. The gateway policy runs before the backend, applies the
> same rules to models from any provider and to MCP tool traffic, and is managed by the platform team in one
> place. Keep both: a request has to pass each of them.

## Add content safety to the model

Pick one track. Each track produces the same policy on your model: **Balanced** (`Medium`) for Hate,
Self-harm, and Sexual, and **Strict** (`Low`) for Violence. The stricter Violence threshold makes the test in
**Verify** more likely to show a block, using only a mild, non-graphic prompt.

<!-- track: portal | Portal -->

### Start the policy wizard

Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway from the gateway switcher.
Select **Policies** › **Add policy**. On the **Type** step, under **Security**, select **Content safety**, then
**Next**.

![The Add policy wizard on the Type step](../assets/screens/policy-add-wizard.png "Policies › Add policy opens a three-step wizard: Type, Scope, Details.")

### Choose the model

On the **Scope** step, select **Individual assets** ("Apply only to selected models, aliases, or MCP servers").
Select your model, then **Next**.

### Set the thresholds

On the **Details** step (**Configure** in some portal versions), under **Parameters**, choose how strictly
each category is filtered:

| Field | Value |
|---|---|
| **Hate** | **Balanced** |
| **Violence** | **Strict** |
| **Self-harm** | **Balanced** |
| **Sexual** | **Balanced** |

Select **Create**. The policy appears in the **Policies** list with your model as its scope.

> **Checkpoint**
> **Policies** lists a **Content safety** policy for your model.

<!-- track: cli | Azure CLI -->

### Set the policy

```bash
az aigateway model policy set-content-safety \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --content-safety Medium --violence-severity Low
```

`--content-safety` sets the default threshold for all four categories. The category overrides
`--hate-severity`, `--self-harm-severity`, `--sexual-severity`, and `--violence-severity` change only their
category, and they require `--content-safety`. Each flag accepts `None`, `Low`, `Medium`, or `High`.

### Confirm the policy

```bash
az aigateway model policy list \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" -o json
```

> **Checkpoint**
> The output contains `"type": "contentSafety"` with `"violenceSeverity": "Low"` and `"Medium"` for the
> other three categories.

<!-- track: rest | REST API -->

### Read the current policies

Policies live inline in the model's `properties.policies` array. A `PATCH` **replaces the whole array**, so
always read it first and keep the policies you didn't mean to change.

```bash
SUB="$(az account show --query id -o tsv)"
URL="https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/service/$GATEWAY/workspaces/default/modelProviders/$PROVIDER/models/$MODEL?api-version=2025-09-01-preview"

az rest --method get --url "$URL" --query properties.policies
```

### Replace the content safety policy and keep everything else

```bash title="Bash"
POLICIES="$(az rest --method get --url "$URL" | jq -c '
  [(.properties.policies // [])[] | select(.type != "contentSafety")]
  + [{"type":"contentSafety","hateSeverity":"Medium","violenceSeverity":"Low","sexualSeverity":"Medium","selfHarmSeverity":"Medium"}]')"

az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}"
```

```powershell title="PowerShell"
$SUB = az account show --query id -o tsv
$URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/service/$GATEWAY/workspaces/default/modelProviders/$PROVIDER/models/$MODEL`?api-version=2025-09-01-preview"

$current  = az rest --method get --url $URL | ConvertFrom-Json
$policies = @($current.properties.policies | Where-Object { $_ -and $_.type -ne 'contentSafety' })
$policies += [pscustomobject]@{
  type = 'contentSafety'; hateSeverity = 'Medium'; violenceSeverity = 'Low'; sexualSeverity = 'Medium'; selfHarmSeverity = 'Medium'
}

$body = @{ properties = @{ policies = $policies } } | ConvertTo-Json -Depth 10 -Compress
$body | Set-Content -Path patch.json
az rest --method patch --url $URL --body '@patch.json'
Remove-Item patch.json
```

> **Checkpoint**
> Running the `GET` again returns your other policies unchanged plus one `contentSafety` entry.

<!-- /tracks -->

## Verify

Test the policy with **benign prompts only**. You don't need harmful content to see how the gateway behaves,
and you should never write it to test a filter.

<!-- steps -->

### Run the test prompts

From the lab folder, run the script for your shell. It sends two prompts: a neutral question, and a request
for a short, non-graphic scene from a historical novel. It prints the status and the start of the response or
the error for each one.

```bash title="Bash"
./infra/test-content-safety.sh "$AI_GATEWAY_MODEL"
```

```powershell title="PowerShell"
./infra/test-content-safety.ps1 -Model $env:AI_GATEWAY_MODEL
```

On GitHub, open [test-content-safety.sh](infra/test-content-safety.sh) or
[test-content-safety.ps1](infra/test-content-safety.ps1).

Example output:

```text
Prompt    Status  Finish reason   Response or error
neutral   200     stop            Teams put an API gateway in front of AI models to centralize access con
fiction   400     -               <the gateway's content safety error message>
```

The neutral prompt returns `200`. The fiction prompt can go either way, and your results will vary: Content
Safety rates both the prompt and the model's response, and a mild battle scene sits close to the **Strict**
Violence threshold. If it returns `400`, the gateway blocked it and the error message says why. If it returns
`200`, the content was rated below the threshold.

> [!IMPORTANT]
> If the fiction prompt passes, don't make it more graphic to force a block. The point of this test is to
> understand thresholds with safe input, not to probe the filter. Use **Monitoring** and real, representative
> traffic in a test environment to tune thresholds.

### Relax one category

Set **Violence** back to **Balanced** (`Medium`) with the track you used, then run the script again. For
example, with the CLI:

```bash
az aigateway model policy set-content-safety \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --content-safety Medium
```

A prompt that **Strict** blocked is more likely to pass at **Balanced**. Prompts that passed before still pass.

### Check the Foundry content filter

Open **Models**, select your model, and find **Content filter** on its details page. That is the Foundry
deployment's own filter, separate from the gateway policy. When Foundry's filter acts instead of the gateway,
the error or the `finish_reason` comes from the backend, and it can mention `content_filter`.

### Find blocked calls in Monitoring

If you configured Application Insights in [Monitor usage, cost, and traces](../13-monitoring/README.md), open
**Monitoring** and look for `400` outcomes on your model. Review them before and after every threshold change.

<!-- /steps -->

> **Checkpoint**
> The neutral prompt returned `200`, you saw how the borderline prompt fared at **Strict** and at **Balanced**,
> and you can tell a gateway block (`400` from the content safety policy) from a Foundry content filter result.

## Go further

- **Screen tool traffic.** Add a **Content safety** policy to the `learn` MCP server from
  [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md). In the wizard, pick the MCP
  server on the **Scope** step. With REST, use the same `contentSafety` object on
  `.../workspaces/default/toolServers/learn`.
- **Make it the default.** Apply **Balanced** content safety to every model and MCP server, including future
  ones, in [Set gateway-wide policy baselines](../09-gateway-baselines/README.md).
- **Tune per category.** Start every category at **Balanced**, tighten the ones that matter most for your
  audience, and turn a category **Off** only with a documented exception.

## Clean up

A **Strict** threshold can block legitimate traffic. Remove the model policy before you continue. The next
lab sets a gateway-wide baseline instead.

<!-- track: portal | Portal -->

### Remove the policy

Select **Policies**, open the **Content safety** policy that's scoped to your model, and delete it.

<!-- track: cli | Azure CLI -->

### Remove the policy

```bash
az aigateway model policy remove \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --remove-content-safety true
```

`policy remove` deletes only the content safety policy and keeps every other policy on the model.

<!-- track: rest | REST API -->

### Remove the policy

```bash
POLICIES="$(az rest --method get --url "$URL" | jq -c '[(.properties.policies // [])[] | select(.type != "contentSafety")]')"
az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}"
```

<!-- /tracks -->

Keep the gateway, model, and key. The next labs reuse them.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Ordinary prompts return `400` | A threshold is too strict for your traffic, or another content safety policy, such as a **Gateway** scope policy, also applies | Review **Policies** for every content safety policy that covers the model. Move categories from **Strict** to **Balanced** and retest with representative prompts. |
| Nothing is ever blocked | The policy is on a different model or alias than the one you call, or a category is **Off** | Check the policy's scope and that the request `model` matches an alias of that model. |
| `400` that mentions `content_filter`, or `finish_reason` is `content_filter` | The Foundry deployment's **Content filter** acted, not the gateway | Review the deployment's content filter in Foundry. The gateway policy is managed separately. |
| `400` that isn't about content | The request itself is invalid, for example an unknown model alias | Read the error message, and check the request body and the alias. |
| `--violence-severity` fails and asks for `--content-safety` | Category overrides need the default threshold | Pass `--content-safety` with the override. |
| `az aigateway: 'model' is misspelled or not recognized` | The CLI extension isn't installed | [Install the extension](https://github.com/Azure/ai-gateway/tree/main/cli#install) and run `az aigateway version`. |

## Next steps

- [Set gateway-wide policy baselines](../09-gateway-baselines/README.md): make content safety the default for
  every model and MCP server.
- [Control which tools agents can call](../05-mcp-tool-controls/README.md): limit which tools agents can reach.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): find `400` outcomes and the policy that caused them.
- Docs: [Policies in AI Gateway](https://ai.gateway.azure.com/docs/policies).
