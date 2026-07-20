# AI Gateway plugin

A coding-agent plugin that helps developers **build applications on top of an
existing [AI Gateway](https://learn.microsoft.com/azure/api-management/)**. It
discovers the models and MCP tool servers registered in a gateway and integrates
them into whatever you're building — call a model over the OpenAI-compatible
passthrough, connect MCP tools, or scaffold a runnable agent — all from your
coding agent.

The plugin follows the [Claude Code plugin spec](https://code.claude.com/docs/en/plugins)
and installs in any compatible coding agent (Claude Code, GitHub Copilot CLI, and
other agents that support the plugin standard).

> **Consumption only.** The plugin is read-only against the gateway — it never
> provisions, updates, or deletes resources. Creating gateways, models, or tools
> is an administrator task done in the AI Gateway Portal.

## What's inside

| Component | Invoked as | Purpose |
| --------- | ---------- | ------- |
| Skill `use-ai-gateway` | `/ai-gateway:use-ai-gateway` | Full discover → select → credential → integrate workflow (call a model, connect MCP tools, or scaffold an agent). |
| Command `discover` | `/ai-gateway:discover` | Read-only: list a gateway's models and MCP tool servers and pick the ones that fit your use case. |
| Command `build` | `/ai-gateway:build` | End-to-end: discover, retrieve a credential, and integrate the models/tools into your app. |

## Install

The plugin is hosted in this repository, so your coding agent can install it
directly from Git — no manual file downloads.

In Claude Code (or any agent that speaks the plugin marketplace protocol):

```
/plugin marketplace add Azure/ai-gateway
/plugin install ai-gateway@ai-gateway
```

## Usage

Point the plugin at your gateway (an ARM resource id or the gateway host) and
describe what you want to build:

```
/ai-gateway:build /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway> a service that summarizes support tickets
```

Or explore first, then integrate:

```
/ai-gateway:discover <gateway-host>
```

## Security

The generated code authenticates the model passthrough and the MCP tool servers
with a gateway **API key**, read from an environment variable
(`AI_GATEWAY_API_KEY`) and never hardcoded. Scaffolded projects keep `.env` out of
source control. If a key is ever exposed, rotate it in the AI Gateway Portal.

To report a security issue, see [SECURITY.md](SECURITY.md).

## Contributing

This project welcomes contributions and suggestions. Most contributions require you
to agree to a Contributor License Agreement (CLA) declaring that you have the right
to, and actually do, grant us the rights to use your contribution. For details,
visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you
need to provide a CLA and decorate the PR appropriately (e.g., status check,
comment). Simply follow the instructions provided by the bot. You will only need to
do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/)
or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any
additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services.
Authorized use of Microsoft trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not
cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or
logos are subject to those third-party's policies.
