---
title: Build on your gateway with coding agents
summary: Install the AI Gateway plugin in GitHub Copilot CLI, Claude Code, Cursor, or Gemini CLI, then let your coding agent discover the gateway's models and MCP tools and generate working client code.
category: agents
level: Beginner
duration: 15
tracks: [code]
order: 17
illustration: diagrams/architecture.svg
tags: [plugin, skills, GitHub Copilot CLI, Claude Code, Cursor, Gemini CLI, MCP, AI_GATEWAY_API_KEY]
objectives:
  - Install the AI Gateway plugin in your coding agent
  - Discover a gateway's models and MCP tool servers from its Azure resource ID
  - Generate and run app code that calls the gateway with a runtime key
  - Review generated code for the right endpoint, model name, and secret handling
prereqs:
  - 02-first-model-call
---

# Build on your gateway with coding agents

Your platform team publishes models and MCP tools behind AI Gateway, and product developers want to use them
without reading gateway settings or passing keys around in chat. The AI Gateway plugin teaches coding agents
such as GitHub Copilot CLI, Claude Code, Cursor, and Gemini CLI what your gateway offers. It then generates
code that uses the right endpoint, model name, and auth header. The plugin only reads from the gateway, so
developers build on top of your governance instead of around it.

![AI Gateway architecture with coding agents among the clients that call one gateway](../assets/diagrams/architecture.svg "Coding agents call the same gateway as apps and agents. The code they generate goes through the gateway's access checks, policies, and telemetry like any other client.")

## Before you begin

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need the
  gateway, a model that answers, and its alias.
- Optional: complete [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md) so the gateway
  also has MCP tools to discover.
- One coding agent, installed and signed in: GitHub Copilot CLI, Claude Code, Cursor, or Gemini CLI. Each agent
  documents its plugin support: [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-finding-installing),
  [Claude Code](https://code.claude.com/docs/en/plugins), [Cursor](https://cursor.com/docs/plugins), and
  [Gemini CLI](https://geminicli.com/docs/extensions/).
- The Azure CLI, signed in with `az login`, with the `aigateway` extension
  ([install it](https://github.com/Azure/ai-gateway/tree/main/cli#install)). The plugin uses your Azure sign-in to
  read the gateway, so your account needs read access to it.
- Python 3.10 or later to run the generated app. To scaffold a standalone agent, you also need the GitHub Copilot
  CLI, because the GitHub Copilot SDK uses it.

Set these variables in the shell that you'll start your coding agent from. Create a key for this app so you can
revoke it on its own later.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export AI_GATEWAY_MODEL="<model-name>"   # the alias from lab 02
export AI_GATEWAY_URL="$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.gatewayUrl -o tsv)"

az aigateway api-key create -g "$RG" --gateway-name "$GATEWAY" \
  -n app-coding-agent --display-name "Coding agent app" -o none
AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets -g "$RG" --gateway-name "$GATEWAY" \
  -n app-coding-agent --query primaryKey -o tsv)" && export AI_GATEWAY_API_KEY
```

```powershell title="PowerShell"
$RG      = "<resource-group>"
$GATEWAY = "<gateway>"
$env:AI_GATEWAY_MODEL = "<model-name>"   # the alias from lab 02
$env:AI_GATEWAY_URL   = az aigateway show -g $RG -n $GATEWAY --query properties.gatewayUrl -o tsv

az aigateway api-key create -g $RG --gateway-name $GATEWAY `
  -n app-coding-agent --display-name "Coding agent app" -o none
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets -g $RG --gateway-name $GATEWAY `
  -n app-coding-agent --query primaryKey -o tsv
```

Then print the gateway's Azure resource ID. You pass it to the plugin.

```bash title="Bash"
az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv
```

```powershell title="PowerShell"
az aigateway show -g $RG -n $GATEWAY --query id -o tsv
```

It looks like
`/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/service/<gateway>`.

## How it works

The plugin bundles one skill and two commands. The skill holds the know-how: which endpoints to call, which
model name the gateway accepts, and how to send the key. The commands run that skill for a task.

Discovery goes through Azure Resource Manager, which is why the plugin needs the resource ID and your Azure
sign-in. Your app then calls the gateway's runtime URL with a runtime key, like any other client. The plugin is
read-only against the gateway: it never creates, updates, or deletes gateways, models, tools, or keys. Creating
those stays an administrator task in the [AI Gateway portal](https://ai.gateway.azure.com).

| Piece | Invoked as | What it does |
|---|---|---|
| Skill `use-ai-gateway` | `/ai-gateway:use-ai-gateway` | The full discover, select, credential, and integrate workflow. The commands use it too. |
| Command `discover` | `/ai-gateway:discover <resource ID>` | Lists the gateway's models and MCP tool servers and suggests the ones that fit your use case. Stops there. |
| Command `build` | `/ai-gateway:build <resource ID> <description>` | Discovers, gets a key, integrates the assets into your app, then runs the code once to check it. |

What the generated code relies on:

| Item | Value |
|---|---|
| Model base URL (OpenAI-compatible) | `<gateway URL>/default/models/openai/v1` |
| MCP endpoint | `<gateway URL>/default/toolservers/<server-name>/mcp` |
| Auth header | `api-key: <runtime key>`. The plugin writes it as `Api-Key`; header names aren't case-sensitive. |
| Key source | The `AI_GATEWAY_API_KEY` environment variable, loaded from a git-ignored `.env` file |
| Model name | The model's deployment name as the gateway publishes it, for example `gpt-4.1-mini` |
| Agent scaffold | GitHub Copilot SDK, `github-copilot-sdk>=1.0.0`, Python unless you ask for TypeScript |

## Install the plugin

<!-- steps -->

### Create a project folder

Start in an empty folder with Git, so you can check later that no secret gets committed.

```bash title="Bash"
mkdir ticket-summarizer && cd ticket-summarizer && git init -q
```

```powershell title="PowerShell"
New-Item -ItemType Directory ticket-summarizer | Out-Null; Set-Location ticket-summarizer; git init -q
```

### Add the plugin to your agent

The plugin lives in the [Azure/ai-gateway](https://github.com/Azure/ai-gateway) repository and follows each
agent's plugin format. In GitHub Copilot CLI and Claude Code, start a session in the folder (`copilot` or
`claude`) and run the slash commands. In Gemini CLI, run the command in your shell, then start `gemini` in the
folder. In Cursor, use the dashboard, then open the folder.

```text title="GitHub Copilot CLI"
/plugin marketplace add Azure/ai-gateway
/plugin install ai-gateway@azure
```

```text title="Claude Code"
/plugin marketplace add Azure/ai-gateway
/plugin install ai-gateway@azure
```

```text title="Cursor"
In the Cursor dashboard, open Plugins and select Add Marketplace.
Import https://github.com/Azure/ai-gateway.
Install ai-gateway from Customize.
```

```bash title="Gemini CLI"
gemini extensions install https://github.com/Azure/ai-gateway
```

The marketplace is named `azure` and the plugin `ai-gateway`.

### Check that the commands are available

In your agent, run the discover command without a resource ID:

```text
/ai-gateway:discover
```

The plugin asks you for the gateway's resource ID before it makes any call. That's how you know it's loaded.
Answer with the ID you printed, or continue with the next step.

<!-- /steps -->

> **Checkpoint**
> `/ai-gateway:discover` is recognized and asks for a gateway resource ID.

## Discover what the gateway offers

<!-- steps -->

### Run discover with your resource ID

Paste the ID that `az aigateway show` printed:

```text
/ai-gateway:discover /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/service/<gateway>
```

When your agent asks to run `az` or `curl` commands, approve the ones that read: getting a token, `GET` requests
to `management.azure.com`, and MCP calls to your gateway URL. Deny any `PUT`, `PATCH`, or `DELETE`. The plugin
never needs them.

### Read the summary

The plugin reads the gateway's runtime URL, lists the models with the exact name each one accepts, and lists the
MCP tool servers with their endpoints. It checks each tool server with a full MCP handshake and reports how many
tools it exposes. Then it highlights the best matches and asks which assets you want. Ask follow-up questions in
plain language, for example:

```text
Which model fits short summaries? Do any tool servers search Microsoft Learn?
```

Discover doesn't retrieve keys or write code. Stop here, or move on to `build`.

<!-- /steps -->

> **Checkpoint**
> The summary lists the model you published in lab 02 and, if you did lab 04, the `learn` tool server.

## Build an app with the gateway

<!-- steps -->

### Describe what to build

Run `build` with the same resource ID and a short description. To use the key you created for this app instead of
letting the plugin pick one, say so in the description:

```text
/ai-gateway:build /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/service/<gateway> a Python command-line script that summarizes a support ticket from a text file. Use the <model-name> model and read the key from the AI_GATEWAY_API_KEY environment variable.
```

Other descriptions to try:

| You want | Describe it as |
|---|---|
| A model call in an app you already have | `add a /summarize endpoint to my FastAPI app that calls the gateway model` |
| Tools in your own MCP client | `connect my app to the learn MCP tools` |
| A ready-to-run agent | `a standalone agent that answers Azure questions with the learn tools` |

### Answer the plugin's questions

`build` runs the discovery again and asks you to confirm the model and tools. Then it gets a key and asks what
you're building, if your description didn't say:

- **Call a model**: code for the OpenAI-compatible endpoint, in your project's language.
- **Connect MCP tools**: configuration for an MCP-capable client or app.
- **Scaffold a standalone agent**: a complete GitHub Copilot SDK project with agent code, `.env`, `.env.example`,
  `.gitignore`, `requirements.txt` or `package.json`, and a `README.md`.

If you didn't name a key, the plugin lists the gateway's keys and reads the secret of an active one. That needs
permission to list key secrets on the gateway. When the plugin writes a key to `.env`, it's a live secret in
plain text, kept out of Git by `.gitignore`.

### Review the generated code

Read the code before you run it again or commit it. Check that:

- The base URL is your gateway URL followed by `/default/models/openai/v1`, or `/default/toolservers/<name>/mcp`
  for tools. Without `/default/`, calls return `404`.
- The `model` value is a name your gateway accepts. To retarget models later without a code change, ask the agent
  to use your alias, as explained in
  [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md).
- The key comes from `AI_GATEWAY_API_KEY` and goes in the `api-key` header. No key value appears in code,
  `README.md`, or config files, and `.env.example` holds only a placeholder.
- `.gitignore` lists `.env`.
- The app calls only the gateway's runtime URL, never `management.azure.com`.
- For a scaffolded agent: `requirements.txt` pins `github-copilot-sdk>=1.0.0`, each MCP server lists the selected
  tools by name instead of `"*"`, and tool permission requests wait for your approval.

### Run the app

`build` already ran the code once and reported the result. Run it yourself from the shell where you set
`AI_GATEWAY_API_KEY`, using the command in the generated `README.md`. For a Python project, that's usually:

```bash title="Bash"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

```powershell title="PowerShell"
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Then start the entry point that the README names, for example `python summarize.py ticket.txt`.

<!-- /steps -->

> **Checkpoint**
> The generated app prints a model response that came through your gateway.

## Verify

<!-- steps -->

### Confirm the key and model outside the generated code

If the app fails, this call tells you whether the problem is in the gateway setup or in the code.

```bash title="Bash"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}"
```

```powershell title="PowerShell"
$body = @{ model = $env:AI_GATEWAY_MODEL; messages = @(@{ role = "user"; content = "ping" }) } | ConvertTo-Json -Depth 5
(Invoke-WebRequest -Method Post -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body -SkipHttpErrorCheck).StatusCode
```

Expect `HTTP 200`.

### Check that no secret can be committed

Run this in the project folder. It checks that Git ignores `.env` and that your key appears in no other file.

```bash title="Bash"
git check-ignore -q .env && echo ".env is ignored" || echo "WARNING: .env is not ignored"
if grep -rIlF --exclude=.env --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules -- "$AI_GATEWAY_API_KEY" .; then
  echo "WARNING: the key appears in the files above"
else
  echo "No key in project files"
fi
```

```powershell title="PowerShell"
git check-ignore -q .env; if ($LASTEXITCODE -eq 0) { ".env is ignored" } else { "WARNING: .env is not ignored" }
$hits = Get-ChildItem -Recurse -File -Force |
  Where-Object { $_.Name -ne ".env" -and $_.FullName -notmatch '[\\/](\.git|\.venv|node_modules)[\\/]' } |
  Select-String -SimpleMatch -Pattern $env:AI_GATEWAY_API_KEY -List
if ($hits) { "WARNING: the key appears in:"; $hits.Path } else { "No key in project files" }
```

Expect `.env is ignored` and `No key in project files`. If the plugin wrote a different key to `.env`, run the
check again with that key in `AI_GATEWAY_API_KEY`.

<!-- /steps -->

> **Checkpoint**
> The direct call returns `200`, the app works, and no key can reach Git.

## Go further

### Use the gateway's tools in VS Code agent mode

VS Code reads MCP servers from `.vscode/mcp.json`. To give agent mode the tools that you federated in
[Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md), save this file as
`.vscode/mcp.json` in your project. Replace `https://<gateway>.azure-api.net` with your gateway URL
(`echo $AI_GATEWAY_URL`) and `learn` with any tool server name that discover listed.

<!-- include: infra/mcp.json -->

On GitHub, open [infra/mcp.json](infra/mcp.json).

Start the server from the `mcp.json` editor and paste your runtime key when VS Code prompts for it. The `inputs`
entry keeps the key out of the file.

### Go keyless

The plugin generates code that uses a runtime key. For production apps, switch to Microsoft Entra ID tokens with
the audience `https://azure-api.net/aigateway`, as shown in
[Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md).

## Clean up

Keep the gateway, model, and alias. Other labs use them.

Delete the key you created for this lab. Then delete the `ticket-summarizer` folder when you're done, because its
`.env` file can hold a live key.

```bash title="Bash"
az aigateway api-key delete -g "$RG" --gateway-name "$GATEWAY" -n app-coding-agent --yes
```

```powershell title="PowerShell"
az aigateway api-key delete -g $RG --gateway-name $GATEWAY -n app-coding-agent --yes
```

If the plugin wrote another gateway key to `.env` and that file was shared or committed, regenerate that key as
shown in [Issue and rotate runtime API keys](../10-api-keys/README.md). Remove the `ai-gateway-learn` entry from
`.vscode/mcp.json` if you added it.

Optionally, remove the plugin. In Cursor, remove it where you installed it.

```text title="GitHub Copilot CLI"
/plugin uninstall ai-gateway
/plugin marketplace remove azure
```

```text title="Claude Code"
/plugin uninstall ai-gateway@azure
/plugin marketplace remove azure
```

```bash title="Gemini CLI"
gemini extensions uninstall ai-gateway
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/ai-gateway:discover` isn't recognized | The plugin isn't installed or the client hasn't reloaded it | Repeat the install for your agent, then restart it. Check with `copilot plugin list` in GitHub Copilot CLI or `gemini extensions list` in Gemini CLI. |
| The plugin can't list models, or Azure returns `401` or `403` | `az` is signed in to another tenant or subscription, or your account can't read the gateway | Run `az account show`, then `az account set --subscription <subscription-id>`. Ask for read access to the gateway. |
| The plugin stops at the credential step | Your account can't list key secrets on the gateway | Create or get a key as in **Before you begin**, and tell the agent to read it from `AI_GATEWAY_API_KEY`. |
| `404 Resource not found` from the gateway | The URL is missing the `/default/` segment | Use `<gateway URL>/default/models/openai/v1` or `<gateway URL>/default/toolservers/<name>/mcp`. |
| `unknown_model` | The model name isn't one the gateway publishes, the client uses another protocol than the model supports, or a GitHub Copilot SDK older than 1.0.0 drops the key header | Use the name that discover reported or your alias. Pin `github-copilot-sdk>=1.0.0`. |
| `401` from the gateway | The key is missing, deleted, or sent in `Authorization` instead of `api-key` | Send the key in the `api-key` header. Create a new key if you deleted it. |
| `KeyError: 'AI_GATEWAY_API_KEY'` | `.env` wasn't loaded, often because PowerShell saved it with a byte order mark | Export the variable in your shell, or save `.env` as UTF-8 without a byte order mark. |
| `429` | A token limit or the backend's quota | The wiring works. See [Throttle tokens per caller with token limits](../06-token-limits/README.md). |
| A tool server shows `0` tools | The server exposes no tools, or tool availability hides them | Check the server's tools in the portal, or see [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md). |

## Next steps

- [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md)
- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md)
- [Deploy a Foundry hosted agent behind AI Gateway](../16-foundry-hosted-agent/README.md)
- [Use the AI Gateway plugin](https://ai.gateway.azure.com/docs/quickstarts/skills) in the AI Gateway docs
