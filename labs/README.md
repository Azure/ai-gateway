# AI Gateway labs

Hands-on labs for the [AI Gateway tier in Azure API Management](https://learn.microsoft.com/azure/api-management/ai-gateway-overview).
Customers and field teams use them to learn the core AI gateway use cases first (models, tools, limits, budgets,
identity, and observability) and then the emerging ones (agents, Agent 365, private networking, and reference
architectures).

**Browse the labs site: [azure.github.io/ai-gateway](https://azure.github.io/ai-gateway/)**

Every lab follows the same structure: a scenario, a diagram of how it works, step-by-step tasks with checkpoints,
a **Verify** section, **Go further** ideas, clean-up, and troubleshooting. Most labs offer several tracks, so you can
follow the one that fits how you work:

| Track | What you use |
|---|---|
| **Portal** | Click-by-click steps in the [AI Gateway portal](https://ai.gateway.azure.com) |
| **CLI** | Azure CLI (`az rest`, `az resource`, `az deployment`) commands for Bash and PowerShell against the `Microsoft.ApiManagement/aigateways` resource |
| **Bicep** | Infrastructure as code in each lab's `infra/` folder, deployed with `az deployment` or `azd` |
| **Code** | Python, TypeScript, and .NET clients, agent frameworks, and REST calls |

## Labs

| # | Lab | Category | Level | Time | Tracks |
|---|---|---|---|---|---|
| 00 | [How Azure AI Gateway works](00-how-ai-gateway-works/README.md) | Foundations | Beginner | 20 min | Portal |
| 01 | [Provision your AI Gateway](01-provision-gateway/README.md) | Foundations | Beginner | 15 min | Portal, CLI, Bicep |
| 02 | [Publish a Foundry model and make your first call](02-first-model-call/README.md) | Foundations | Beginner | 25 min | Portal, CLI, Bicep, Code |
| 03 | [Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md) | Models & routing | Intermediate | 30 min | Portal, REST |
| 04 | [Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md) | MCP & tools | Beginner | 25 min | Portal, CLI, Bicep, Code |
| 05 | [Control which tools agents can call](05-mcp-tool-controls/README.md) | MCP & tools | Intermediate | 20 min | Portal, REST |
| 06 | [Throttle tokens per caller with token limits](06-token-limits/README.md) | Governance & cost | Beginner | 25 min | Portal, CLI, REST, Bicep |
| 07 | [Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | Governance & cost | Intermediate | 30 min | Portal, REST |
| 08 | [Screen prompts and responses with content safety](08-content-safety/README.md) | Governance & cost | Beginner | 20 min | Portal, CLI, REST |
| 09 | [Set gateway-wide policy baselines](09-gateway-baselines/README.md) | Governance & cost | Intermediate | 25 min | Portal, REST, Bicep |
| 10 | [Issue and rotate runtime API keys](10-api-keys/README.md) | Security & identity | Beginner | 15 min | Portal, CLI |
| 11 | [Go keyless with Microsoft Entra ID and RBAC](11-entra-rbac/README.md) | Security & identity | Intermediate | 35 min | Portal, CLI, Code |
| 12 | [Call backends with managed identities](12-backend-identity/README.md) | Security & identity | Intermediate | 20 min | Portal, CLI, Bicep |
| 13 | [Monitor usage, cost, and traces](13-monitoring/README.md) | Observability & FinOps | Beginner | 25 min | Portal, Bicep |
| 14 | [Attribute tokens and cost with OpenTelemetry](14-otel-chargeback/README.md) | Observability & FinOps | Advanced | 35 min | Portal, REST |
| 15 | [Connect agent frameworks to models and tools](15-agent-frameworks/README.md) | Agents | Intermediate | 30 min | Code |
| 16 | [Deploy a Foundry hosted agent behind AI Gateway](16-foundry-hosted-agent/README.md) | Agents | Intermediate | 40 min | Portal, CLI, Code |
| 17 | [Build on your gateway with coding agents](17-coding-agent-plugin/README.md) | Agents | Beginner | 15 min | Code |
| 18 | [Lock down backend traffic with private networking](18-private-networking/README.md) | Production & emerging | Advanced | 45 min | Portal, CLI, Bicep |
| 19 | [Protect tool calls with Agent 365 threat protection](19-tool-threat-protection/README.md) | Production & emerging | Advanced | 30 min | Portal |
| 20 | [Govern MCP servers with Agent 365](20-agent-365-governance/README.md) | Production & emerging | Intermediate | 20 min | Portal |
| 21 | [Deploy an enterprise reference architecture](21-enterprise-reference/README.md) | Production & emerging | Advanced | 60 min | Bicep |

New to AI Gateway? Start with labs 00 to 02 (the **30-minute quickstart** path on the site), then follow the path for
your role: platform engineer, app and agent developer, security and compliance, or FinOps and operations.

## Prerequisites

- An Azure subscription where you can create resources. AI Gateway is in public preview in **East US 2**
  (`eastus2`) and **Sweden Central** (`swedencentral`); each lab lists what it needs under **Before you begin**.
- For the CLI and Bicep tracks: Azure CLI 2.75.0 or later, Bicep, and `jq` for the Bash snippets. Every lab
  creates the dedicated `Microsoft.ApiManagement/aigateways` resource type. The CLI track calls the Azure Resource
  Manager REST API with `az rest`, because the `az aigateway` extension doesn't manage the new `aigateways`
  resource type yet.
- For the Code track: Python, Node.js, or the .NET 8 SDK, depending on the sample. Each lab lists the exact
  versions under **Before you begin**.

> [!NOTE]
> The labs are written against a preview service. Portal labels and API shapes can change; each lab links to the
> product documentation it's based on. If something doesn't match, please open an issue.

## Work on the labs site

The site is a static build of these Markdown files. Lab sources live in `labs/<NN-slug>/README.md` and render on
GitHub as-is; the build turns them into the site in [`docs/`](../docs), which GitHub Pages serves from the `main`
branch.

```bash
cd labs
npm install
npm run dev        # build, watch, and serve at http://localhost:4173/ai-gateway/
npm run check      # strict build: fails on broken links, anchors, images, or front matter
npm run diagrams   # regenerate the SVG diagrams in assets/diagrams
```

To publish a copy to Azure Static Web Apps (served from `/`), sign in with `az login` and run
`npm run deploy:swa -- [app-name] [resource-group]`. It defaults to `swa-ai-gateway-labs` in `rg-ai-gateway-labs`,
builds into the ignored `labs/.swa` folder, and deploys with the Static Web Apps CLI. `docs/` isn't touched.

Commit both your changes under `labs/` and the regenerated `docs/` folder, and run `npm run check` before you open
a pull request.

| Path | Contents |
|---|---|
| `NN-slug/README.md`, `NN-slug/infra/` | A lab and its scripts, Bicep, and samples |
| `catalog.json` | Categories, learning paths, use cases, and short titles |
| `assets/` | Portal screenshots, provider logos, illustrations, and generated diagrams |
| `site/` | Page templates, Markdown extensions, CSS, and JavaScript (including the interactive simulators) |
| `build.mjs`, `tools/` | The site build, local server, and diagram generator |

Read [AUTHORING.md](AUTHORING.md) for the front matter, the directives for tracks, steps, widgets, and includes,
and the writing conventions every lab follows.
