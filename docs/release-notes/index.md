# Labs release notes

What changed in the Azure AI Gateway labs for each [product release](https://ai.gateway.azure.com/docs/), and
where to practice every new feature. Newest first. 🆕 marks a new lab, ✏️ an updated lab, ✅ a lab that already
covered the feature, and ➖ a feature that no lab covers yet.

## October 16, 2026

### Priority and weighted model routing, MCP 2026-07-28

Keep a stable alias while you prefer purchased capacity, balance traffic across deployments, or test a new
model version, and manage MCP servers that use the 2026-07-28 MCP specification.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-16).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Route an alias's traffic across backend models by priority and weight | [22 · Route an alias across models by priority and weight](22-model-routing/README.md) | 🆕 New lab |
| Canary a new model version or run an A/B test with a controlled split | [22 · Split traffic 80/20 between two models](22-model-routing/README.md#split-traffic-8020-between-two-models) | 🆕 New lab |
| Prefer purchased capacity with priorities | [22 · Prefer one model by priority](22-model-routing/README.md#prefer-one-model-by-priority) | 🆕 New lab |
| Create and edit aliases with the **Create alias** wizard | [03 · Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md#give-one-backend-model-two-aliases) | ✏️ Updated |
| Choose the MCP protocol versions a server supports, including 2026-07-28 | [04 · Choose supported MCP versions](04-federate-mcp-tools/README.md#choose-supported-mcp-versions) | ✏️ Updated |
| See supported MCP versions on the server page and in **Catalog** | [04 · Check the negotiated version](04-federate-mcp-tools/README.md#check-the-negotiated-version) | ✏️ Updated |

#### Labs changes

- **October 26.** The Bicep templates now follow the AI Gateway [reference sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/infra/ai-gateway/main.bicep): they
  create the gateway in the `Consumption` SKU, the same one that `az aigateway create` uses, and then its connector
  gateway. A template that omits `sku` creates a `Premium` gateway, so set it in your own templates too. Every
  template now silences the `BCP081` warnings for the preview resource types, so `az bicep build` runs clean, and
  the quick start template's model and alias set `displayName`, `modelVersion`, and `aliasName`, as the sample does.
  [Lab 01](01-provision-gateway/README.md#review-the-template) explains the template, and its troubleshooting now
  covers `InvalidSkuName` and the limit of five gateways per subscription in each region.
- **October 23.** The Azure CLI tracks, the **Verify** and **Clean up** steps, and the lab scripts now use the
  `aigateway` CLI extension for gateways, model providers, aliases, API keys, and MCP servers.
  [Lab 01](01-provision-gateway/README.md#before-you-begin) shows how to install it. The labs keep `az rest` only
  for what the extension can't do yet, such as registering models and setting policies, and say why each time.
- **October 23.** [Lab 18](18-private-networking/README.md#prepare-the-virtual-network) now delegates the integration
  subnet to `Microsoft.App/environments`, which the service requires. A subnet delegated to
  `Microsoft.Web/serverFarms` fails with `AIGatewaySubnetNotDelegated`. The portal's subnet check still expects
  `Microsoft.Web/serverFarms` and shows a warning, which you can ignore.
- **October 23.** [Lab 24](24-github-copilot-byok/README.md#publish-microsoft-learn-tools-for-copilot) now
  publishes the Microsoft Learn MCP server on the gateway, with portal, Azure CLI, and Bicep tracks, and adds its
  tools to GitHub Copilot in VS Code, the Copilot CLI, the Copilot SDK, and the GitHub Copilot app with the same
  runtime key. It shows the token cost of tool results and how one suspended key cuts off both models and tools.
- **October 22.** New lab [24 · Use your gateway's models and tools in GitHub Copilot](24-github-copilot-byok/README.md):
  publish `gpt-6-astra` with a per-caller token limit and a key for Copilot, then connect GitHub Copilot in VS Code,
  the Copilot CLI, the Copilot SDK (Python and TypeScript), and the GitHub Copilot app with bring your own key
  (BYOK). It includes portal, Azure CLI, and Bicep tracks, and shows how one suspended key cuts off every Copilot
  surface.
- **October 22.** New [5-minute quick start](quickstart/README.md): learn the five building blocks, create a gateway
  with a Foundry `gpt-6-luna` model, an alias, and a runtime key, and make your first call. Follow it in the AI
  Gateway portal, with a screenshot for every step; paste its Azure CLI commands (Bash or PowerShell) into Cloud
  Shell; or download its Bicep template and deploy it with one `azd up`. There's nothing to clone. The
  home page now starts with it, and the former 30-minute quickstart path is now **30-minute essentials**.
- **October 22.** New lab [23 · Stream responses and count every token](23-streaming-responses/README.md), which
  covers usage for streamed Chat Completions responses from the [September 24](#september-24-2026) release. It
  streams with curl, PowerShell, Python, and TypeScript, shows each chunk and where usage arrives, proves that a
  token limit counts streams with or without `include_usage`, and has a notebook and an interactive streaming
  usage simulator on the site.
- **October 22.** New lab [22 · Route an alias across models by priority and weight](22-model-routing/README.md),
  with portal, Azure CLI, and Bicep tracks, a script that counts which model served each request, and an
  interactive priority and weight simulator on the site.
- **October 22.** [Lab 04](04-federate-mcp-tools/README.md) adds **Supported MCP versions**: the version list,
  the legacy defaults, the rule that every backend must support every listed version, and a `supportedVersions`
  Bicep parameter. [Lab 03](03-multi-provider-aliases/README.md) follows the new alias wizard and links to lab 22.
- **October 22.** The labs use the latest models: `gpt-6-luna` and `gpt-6.1-sol` from Microsoft Foundry, and
  `claude-haiku-5-5` and `claude-sonnet-5-5` from Anthropic. Portal steps say **Catalog** where the portal used
  to say **Discover**.
- **October 22.** [Lab 00](00-how-ai-gateway-works/README.md) has a narrated three-minute video tour of the
  portal.
- **October 19.** Every lab creates the dedicated `Microsoft.ApiManagement/aigateways` resource type.
- **October 19.** Each lab's `README.md` is the source of truth for both the site and GitHub, with navigation
  that works on GitHub. Jupyter notebooks run five labs end to end by deploying the labs' own Bicep files
  through a shared [`utils.py`](shared/utils.py).
- **October 19.** [Lab 01](01-provision-gateway/README.md) has a narrated video, and the
  [`azure-ai-gateway-labs`](skills/azure-ai-gateway-labs/SKILL.md) agent skill teaches coding agents how to use
  the labs.

## October 8, 2026

### Agent 365 integration and tool threat protection

Discover and govern AI Gateway MCP servers and tools from Microsoft Agent 365, and protect tool calls with
Microsoft Defender and Microsoft Purview.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-08).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Discover AI Gateway MCP servers in the Agent 365 inventory | [20 · Connect Agent 365 to your gateways](20-agent-365-governance/README.md#connect-agent-365-to-your-gateways) | ✅ Covered |
| Block or unblock MCP servers and individual tools from Agent 365 | [20 · Block a tool](20-agent-365-governance/README.md#block-a-tool) | ✅ Covered |
| Evaluate tool calls before and after invocation with Defender and Purview | [19 · Protect tool calls with Agent 365 threat protection](19-tool-threat-protection/README.md) | ✅ Covered |

#### Labs changes

- **October 14.** The labs launch with 22 labs that cover every product release through October 8, each with
  portal steps and, where the product supports them, Azure CLI, REST, Bicep, and code tracks.

## October 1, 2026

### Cost limit overrides for Microsoft Entra identities

Set different cost limit amounts for Microsoft Entra callers by identity or by an exact combination of
validated token claims.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-01).

| In the product | Practice it in the labs | Status |
|---|---|---|
| A higher or lower budget for a selected identity or matching token claims | [07 · Give a Microsoft Entra identity its own budget](07-cost-budgets/README.md#give-a-microsoft-entra-identity-its-own-budget) | ✅ Covered |
| Separate budgets per caller by tenant ID and object ID | [07 · Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | ✅ Covered |
| The first matching override wins | [07 · How it works](07-cost-budgets/README.md#how-it-works) | ✅ Covered |

## September 24, 2026

### Model aliases, Entra access, and Chat Completions streaming usage

Aliases become the stable model contract, with Microsoft Entra authentication, gateway-scoped policies, and
complete usage for streamed Chat Completions responses.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-09-24).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Callable aliases, several aliases for one backend model, and retargeting | [03 · Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md) | ✅ Covered |
| Grant model and MCP access to Microsoft Entra users, groups, apps, and managed identities | [11 · Go keyless with Microsoft Entra ID and RBAC](11-entra-rbac/README.md) | ✅ Covered |
| Export selected JWT claims to OTLP logs, traces, and metrics | [14 · Choose the claims to export](14-otel-chargeback/README.md#choose-the-claims-to-export) | ✅ Covered |
| Apply one policy to every current and future asset, including a gateway-wide cost limit | [09 · Set gateway-wide policy baselines](09-gateway-baselines/README.md) | ✅ Covered |
| Usage for streamed Chat Completions responses without `include_usage` | [23 · Stream a burst without asking for usage](23-streaming-responses/README.md#stream-a-burst-without-asking-for-usage) | 🆕 New lab |

## September 10, 2026

### Per-key budget overrides and MCP tool filtering and blocking

Assign higher or lower model budgets to selected API keys, and control which MCP tools agents can discover and
invoke.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-09-10).

| In the product | Practice it in the labs | Status |
|---|---|---|
| A different budget for selected API keys | [07 · Give an API key a bigger budget](07-cost-budgets/README.md#give-an-api-key-a-bigger-budget) | ✅ Covered |
| Expose all, selected, or pattern-matched tools | [05 · Publish only approved tools](05-mcp-tool-controls/README.md#publish-only-approved-tools) | ✅ Covered |
| Block individual tools or a whole MCP server | [05 · Take the whole server offline](05-mcp-tool-controls/README.md#take-the-whole-server-offline) | ✅ Covered |
| Redesigned Home and first-run gateway setup | [01 · Provision your AI Gateway](01-provision-gateway/README.md) | ✅ Covered |

## August 28, 2026

### OpenTelemetry observability and model budgets

Export logs, traces, token metrics, and estimated cost metrics through OTLP, and enforce model spend with cost
limits.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-08-28).

| In the product | Practice it in the labs | Status |
|---|---|---|
| The built-in Application Insights dashboard and request traces | [13 · Monitor usage, cost, and traces](13-monitoring/README.md) | ✅ Covered |
| OTLP export of logs, traces, and token and cost metrics | [14 · Attribute tokens and cost with OpenTelemetry](14-otel-chargeback/README.md) | ✅ Covered |
| Cost limits with hourly to yearly budget windows | [07 · Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | ✅ Covered |
| Import Microsoft Foundry models and onboard custom providers | [02 · Publish a Foundry model](02-first-model-call/README.md) and [03 · Add Anthropic as a custom provider](03-multi-provider-aliases/README.md#add-anthropic-as-a-custom-provider) | ✅ Covered |

## How these notes work

Each section matches one entry in the [product release notes](https://ai.gateway.azure.com/docs/), with the same
date and title, and maps every product change to the lab where you can practice it. Changes to the labs that
don't come from a product release are listed under **Labs changes** in the release they followed.

This file, [`labs/RELEASE-NOTES.md`](RELEASE-NOTES.md), is the source of truth: the labs site renders it at
[/release-notes/](https://azure.github.io/ai-gateway/release-notes/). To check for product releases that the
notes don't cover yet, run `npm run releases` in `labs/`. See [Authoring](AUTHORING.md#release-notes).
