# Authoring Azure AI Gateway labs

Every lab is a folder under `labs/`. Its `README.md` is the **single source of truth** for two views: a rich page
on the **labs site** (`docs/`, published with GitHub Pages) and a self-contained lab you can follow **on GitHub**.
`npm run build` in `labs/` generates the site and refreshes the GitHub navigation in the READMEs (see
[GitHub view](#github-view)). Don't edit files in `docs/` by hand.

```text
labs/
├── catalog.json                 # categories, learning paths, use-case map
├── assets/                      # shared images: screens/, diagrams/, providers/
├── 06-token-limits/
│   ├── README.md                # the lab (metadata + Markdown + generated GitHub chrome)
│   ├── 06-token-limits.ipynb    # optional: the lab as a Jupyter notebook
│   └── infra/                   # optional: Bicep, scripts, sample code referenced by the lab
└── site/                        # site engine (templates, CSS, JS) – not lab content
```

## Metadata

Start the README with YAML metadata wrapped in an HTML comment, so GitHub hides it. The first line must be exactly
`<!--`. Classic `---` front matter also works; `npm run sync` converts it.

```yaml
<!--
title: Throttle tokens per caller with token limits     # sentence case, outcome-oriented
summary: One or two sentences shown on catalog cards and in search.
category: governance            # foundations | models | tools | governance | security | observability | agents | production
level: Beginner                 # Beginner | Intermediate | Advanced
duration: 25                    # minutes, realistic for a first-timer
tracks: [portal, cli, rest, iac] # portal | cli | iac | code | rest – only tracks the lab really offers
order: 6                        # catalog order (matches folder number)
status: new                     # optional: new | preview | emerging
illustration: diagrams/token-limits.svg   # optional, relative to labs/assets/
tags: [tokenLimit, 429, TPM]
objectives:                     # 3–5 measurable outcomes ("You will …" is implied)
  - Explain how token limits are counted per caller identity
  - Add a token limit policy in the portal, with the CLI, or with REST
  - Trigger and interpret a 429 response with Retry-After
prereqs:                        # lab folder names, rendered as links
  - 02-first-model-call
-->
```

## GitHub view

`npm run sync` (also run by `npm run build`) reads the metadata and `catalog.json` and adds GitHub-only chrome to
each README, so the lab reads well on github.com:

| Generated | What readers see on GitHub |
|---|---|
| `nav` region above the H1 | Breadcrumb back to the lab catalog and the lab's category |
| `intro` region below the H1 | Summary, a time, level, tracks, and prerequisites table, the objectives, links to the interactive version, the notebook, and `infra/`, and an **On this page** list of the H2 sections |
| `<details>` lines around tracks | Each track becomes a collapsible section; the first one is open |
| `<details>` lines around titled code blocks | Bash/PowerShell (and other) tab groups become collapsible sections |
| `include` region after `<!-- include: … -->` | The included file's code, with a link to the file; files over 28 lines are collapsed |
| `widget` region after `<!-- widget: … -->` | A pointer to the interactive simulator on the site |
| `footer` region at the end | Previous lab, all labs, next lab, and the learning paths that contain the lab |

It also refreshes the `badges`, `paths`, `catalog`, and `notebooks` regions of [`labs/README.md`](README.md).

Generated regions sit between `<!-- gh:begin … -->` and `<!-- gh:end -->`; generated single lines end with
`<!-- gh -->`. Don't edit them: sync rewrites them from the metadata, and the site build strips them before
rendering, so the site never shows them. Write everything else as usual. After you change a lab, its metadata,
an included file, or `catalog.json`, run `npm run sync` and commit the README changes. `npm run check` fails if a
README is out of sync.

## Lab anatomy

Use these H2 sections in this order. Keep the H1 identical to `title`.

1. `# Title` then a 2–4 sentence **scenario** paragraph: who has the problem and why the gateway solves it.
   Follow with the illustration (`![…](../assets/diagrams/x.svg)`) and, when useful, an interactive widget.
2. `## Before you begin` – tools, permissions, and the outputs of prerequisite labs. Link prerequisites.
3. `## How it works` – the concept in under 200 words, a table of key values, and a widget or diagram.
4. One or more task sections (for example `## Add a token limit`). Put multi-track instructions in
   track tabs. Each `###` heading inside a track becomes a numbered step with a **Done** checkbox.
5. `## Verify` – prove it works. End major tasks with a **Checkpoint** callout.
6. `## Clean up` – always present. Say what is safe to delete and what is shared with other labs.
7. `## Troubleshooting` – a table of symptoms, causes, and fixes.
8. `## Next steps` – 2–4 links to related labs and docs.

## Markdown conventions

All conventions are HTML comments or standard GitHub Markdown, so the README still reads cleanly on GitHub.

### Track tabs

````markdown
<!-- track: portal | Portal -->
### Open the policy wizard
In the [AI Gateway portal](https://ai.gateway.azure.com), select **Policies** › **Add policy**.

<!-- track: cli | Azure CLI -->
### Set the policy
```bash
az rest --method patch --url "$WS/modelProviders/$PROVIDER/models/$MODEL?$API" --body @policies.json
```

<!-- /tracks -->
````

- Consecutive `<!-- track: id | Label -->` markers form one tab group; `<!-- /tracks -->` closes it.
- Track ids: `portal`, `cli`, `iac`, `code`, `rest`. The reader's choice is remembered across labs.
- Each `###` inside a track is a step. Keep steps small: one screen or one command block.
- Use `<!-- steps -->` … `<!-- /steps -->` to number `###` steps outside track tabs.

### Click paths

Write UI navigation as bold items separated by `›`: `**Policies** › **Add policy** › **Token rate limit**`.
These render as breadcrumb chips. Use the exact portal labels listed in the facts sheet.

### Placeholders

Use these placeholders in commands and URLs. On the site, readers can enter their values once and every
code block updates (values are stored in the browser; secrets are never stored):

`<subscription-id>` `<resource-group>` `<gateway>` `<location>` `<model-name>` `<provider-name>`
`<foundry-account-name>` `<tenant-id>`

For secrets, use shell variables (`$AI_GATEWAY_API_KEY`) and show how to set them, never inline values.

### Code blocks

- Always set the language. Add `title="…"` to label a block.
- Two or more **adjacent** titled blocks become language tabs (for example `title="Bash"` and
  `title="PowerShell"`, or `title="Python"` / `title="TypeScript"` / `title="C#"`). The choice is synced across the page.
- Include files from the lab folder: `<!-- include: infra/main.bicep -->` (optional language: `<!-- include: infra/x.sh bash -->`).
  The site shows the file with a GitHub link and collapses long files. On GitHub, add a normal link next to it.

### Callouts and checkpoints

```markdown
> [!TIP]
> Start limits above observed traffic, then lower them with evidence.

> **Checkpoint**
> `az rest --url "$MODEL_URL?$API" --query properties.policies` shows a `tokenLimit` entry with `count: 1000`.
```

Kinds: `NOTE`, `TIP`, `IMPORTANT`, `WARNING`, `CAUTION`. A blockquote starting with **Checkpoint**,
**Verify**, or **Check your work** becomes a green checkpoint.

### Images and diagrams

- Paths are relative to the README: `![Alt text](../assets/screens/monitoring-overview.png "Caption")`.
- SVG diagrams in `../assets/diagrams/` are inlined on the site (theme-aware, animated).
- Screens available in `assets/screens/`: `monitoring-overview.png`, `monitoring-trace.png`,
  `policy-cost-limit-details.png`, `monitoring-token-claim-attributes.png`, `models-aliases.png`,
  `mcp-tool-controls.png`, `policy-add-wizard.png`, `policy-gateway-scope.png`,
  `policy-cost-limit-entra-overrides.png`, `policy-tool-threat-protection.jpeg`,
  `access-entra-role-assignments.png`, `managed-identities.png`.
- Diagrams in `assets/diagrams/`: `architecture.svg`, `request-lifecycle.svg`, `aliases.svg`,
  `mcp-federation.svg`, `policy-scopes.svg`, `identity-boundaries.svg`, `observability.svg`,
  `private-networking.svg`, `hosted-agent.svg`, `agent-365.svg`, `threat-protection.svg`, `token-limits.svg`.
- Provider logos in `assets/providers/`: `microsoft-foundry.png`, `azure-openai.png`, `openai.png`,
  `anthropic.png`, `aws-bedrock.png`, `google-vertex.png`, `custom-models.png`.

### Interactive widgets

`<!-- widget: name {"json":"config"} -->` mounts a simulator on the site (invisible on GitHub, so
never put essential instructions in a widget).

| Widget | Purpose | Config |
|---|---|---|
| `request-lifecycle` | Animated request through auth → policies → backend → telemetry, with failure toggles | `{"focus":"tokenLimit"}` optional |
| `token-limit` | Rolling-window token limit simulator with 429 and Retry-After | `{"limit":1000,"period":"minute"}` |
| `request-rate` | Calls-per-window simulator for tools | `{"calls":5,"window":30}` |
| `tool-patterns` | Try allow and block patterns against a tool catalog | `{"tools":["learn_search","…"],"allow":["*"],"block":["*delete*"]}` |
| `budget` | Cost-limit simulator with per-key overrides | `{"amount":5,"period":"day"}` |
| `alias-retarget` | Retarget an alias between backend models without client changes | none |
| `policy-layers` | Which gateway and asset policies apply to a request | none |

## Writing style

- Second person, present tense, active voice. Sentence-case headings. Short paragraphs.
- Lead with the outcome. Explain *why* before *how* in one or two sentences, then give exact steps.
- Use exact portal labels in bold. Never invent UI labels, CLI flags, or JSON fields. When automation for a
  feature isn't documented, give the portal path and say so.
- Every command must be copy-pasteable. Prefer environment variables set once at the top of a track.
- Bash first, PowerShell as an adjacent tab where it matters.
- Mark preview behavior. The AI Gateway tier is in public preview in East US 2 and Sweden Central.
- Always include clean-up instructions and point out billable resources.

## Infrastructure as code

- Bicep files live in the lab's `infra/` folder and must compile: `az bicep build --file infra/main.bicep --stdout > /dev/null`.
  `BCP081` warnings for preview types are acceptable.
- Use API version `2025-09-01-preview` for `Microsoft.ApiManagement/*` resources.
- Gateways are the dedicated `Microsoft.ApiManagement/aigateways` type, never `Microsoft.ApiManagement/service`.
  Create a `Microsoft.Web/connectorGateways` resource with the same name first (API version `2026-05-01-preview`),
  as [lab 01's template](01-provision-gateway/infra/main.bicep) does. Don't set `sku` or publisher properties.
  Gateway names have 24 characters or fewer, and the runtime URL is `https://` plus
  `properties.frontend.defaultHostname` (`<name>.<region>-01.ai.gateway.azure.com`).
- Policy `counterKey` values are arrays: `counterKey: [ 'identity' ]` or `[ 'ipAddress' ]`.
- CLI tracks call ARM with `az rest`, because the `az aigateway` extension doesn't manage `aigateways` yet.
  Set `GATEWAY_ID`, `GW`, `WS` (`$GW/workspaces/default`), and `API` (`api-version=2025-09-01-preview`) once at the
  top of the track. `PATCH` replaces whole arrays such as `properties.policies`, so read, edit, then write.
- Parameterize names and locations; default `location` to `resourceGroup().location`.
- Mirror the structure of the existing labs: lab 01 for a single template, lab 21 for modules, and lab 16 for an
  azd project.
- Python hosted agents ship a pinned `requirements.txt`. Don't ship a `pyproject.toml` without its `uv.lock`, because
  the Foundry remote build then treats the project as Poetry and fails. Never commit lock files that point to a private
  package index.

## Runtime calls

- The model endpoint (`<gateway URL>/default/models/openai/v1`) accepts a runtime key in the `api-key` header, the
  same key as `Authorization: Bearer <key>`, or a Microsoft Entra token. With an OpenAI SDK, pass the key as the
  client's API key and add no `api-key` header: a request with both headers fails with `400` "Specify either an API
  key or an Authorization header, not both".
- The MCP endpoint (`<gateway URL>/default/toolservers/<name>/mcp`) reads keys only from the `api-key` header. A
  bearer token there must be a Microsoft Entra token.
- The gateway publishes federated tools as `<namespace>_<tool>`, with one underscore, for example
  `learn_microsoft_docs_search`.

## Notebooks

Some labs ship a Jupyter notebook, `NN-slug/NN-slug.ipynb`, that runs the lab end to end from Python. The build
finds it automatically: the lab page gets a **Notebook** button, and the GitHub header, the catalog, and the
**Run the notebooks** table link to it. Follow the structure of the existing notebooks:

1. A Markdown intro: the H1, a one-line flow of what the notebook builds, a table of the resources it uses,
   prerequisites (`az login`, Python 3.10 or later), and a note to select **Run All**.
2. A `%pip install` cell with only the packages the notebook needs.
3. **0. Initialize variables**: the shared defaults (resource group `rg-ai-gateway-labs`, gateway
   `aigw-labs-<6 characters of the SHA-1 of the subscription ID>`, region `eastus2`) that the environment variables
   `AIGW_RESOURCE_GROUP`, `AIGW_GATEWAY_NAME`, and `AIGW_LOCATION` override, the signed-in subscription from
   `az account show`, and `AzureCliCredential`. Stop with a clear `❌` message when a prerequisite is missing.
4. Numbered steps that mirror the lab's sections. Each step has a short Markdown explanation and a code cell that
   reuses existing resources, waits for long operations, and checks the result with `assert`.
5. **Clean up** (delete only what the notebook created), **Troubleshooting**, and **Next steps**.

Never print or save keys or tokens. Run the notebook from start to finish against a real subscription before you
commit it, then clear all outputs (`jupyter nbconvert --clear-output --inplace <file>`).

## Build and preview

```bash
cd labs
npm install
npm run build          # syncs the GitHub chrome, then writes ../docs
npm run sync           # only refresh the GitHub chrome in the READMEs and labs/README.md
npm run check          # strict build: fails on warnings, including out-of-sync READMEs
npm run serve          # http://localhost:4173
npm run watch          # rebuild on change
```
