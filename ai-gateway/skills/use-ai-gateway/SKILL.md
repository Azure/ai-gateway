---
name: use-ai-gateway
version: 2.0.0
updated: 2026-07-20
description: Discover the models and MCP tool servers registered in an AI Gateway, retrieve a credential, and integrate them into any application — call a model over the OpenAI-compatible passthrough, connect to MCP tool servers, or scaffold a standalone agent. Use this whenever a developer wants to use an AI Gateway's models and/or tools from the app they are building.
---

# Use an AI Gateway (models & MCP tools)

<!-- Skill version 2.0.0 (2026-07-20). Canonical copy shipped by the `ai-gateway` plugin. Works with any coding agent that can read this file. -->

> Invoked as `/ai-gateway:use-ai-gateway` when installed via the plugin. It is also invoked automatically by the `/ai-gateway:discover` and `/ai-gateway:build` commands.

> This skill is coding-agent–agnostic: any assistant that can read this file and run shell commands can follow it.

Use this skill when a developer wants to **use the models and/or MCP tools registered in an existing AI Gateway from their application** — whatever they are building (a web app, backend service, script, notebook, data pipeline, or a standalone agent). This single skill takes the user all the way from discovery to working, integrated code:

1. **Discover** the models and MCP tools registered in the gateway.
2. **Select** the ones that match the user's intent (and confirm with them).
3. **Retrieve** the credential needed to call them.
4. **Integrate** them into the user's application, choosing the path that fits what they're building:
   - **Call a model** over the gateway's OpenAI-compatible passthrough (any language, framework, or raw HTTP).
   - **Connect MCP tools** from an MCP-capable client/app.
   - **Scaffold a standalone agent** (GitHub Copilot SDK) if the user wants a ready-to-run agent project.

## Scope (consumption only)

This skill is **strictly for developers consuming an existing AI Gateway**. It is **read-only** against the gateway and only generates client code that calls already-registered models and tools.

- ✅ Allowed: list models, list tools/MCP servers, read an existing API key, generate integration/client/agent code.
- ❌ Not allowed: creating, provisioning, updating, or deleting gateways, models, tools, connections, products, or any other resource. Never issue ARM `PUT`/`PATCH`/`DELETE` calls. If a user asks to create or provision a gateway or model, tell them that is an administrator task done in the AI Gateway Portal and is out of scope for this skill.

---

## Part 1 — Discover & select assets

### Parameters

Ask the user for (or confirm) these before calling the API:

- **gatewayResourceId** — the ARM resource ID of the user's gateway, e.g.
  `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway-name>`. Keep the **leading `/`** exactly as ARM returns the `id`. The URL templates below append it directly to `https://management.azure.com` (no slash in between), so the full URL resolves to `https://management.azure.com/subscriptions/...`. Don't add a slash before a leading-slash id — that produces a doubled `//subscriptions/...` and the call fails.
- **apiVersion** — `2025-09-01-preview`

Every ARM call must be authenticated with an Azure Resource Manager bearer token:

```
Authorization: Bearer <token>
```

Retrieve the token with:

```
az account get-access-token --query accessToken -o tsv
```

### 1. Discover models

List the models registered in the gateway workspace:

```
GET https://management.azure.com{gatewayResourceId}/workspaces/default/models?api-version={apiVersion}
```

**Use `properties.deployment.modelName` as the model identifier** in every gateway call — **not** the ARM resource `name` and **not** `properties.displayName`. This is the single most common cause of failures, so get it right:

- `properties.deployment.modelName` is the exact string the OpenAI passthrough accepts in the request body, e.g. `gpt-5.4-nano` or `DeepSeek-V3.2`. It preserves dots and original casing.
- The ARM resource `name` is a **sanitized** version of that value with dots and other characters replaced by dashes (e.g. `gpt-5-4-nano`). Sending the ARM `name` to the passthrough is rejected with a misleading **`unknown_model`** error.
- `properties.displayName` is a human-friendly label and is also rejected by the passthrough.

For each model, read `properties.deployment.modelName` and carry that exact string (same dots, same casing, same punctuation) through to the agent's `model=` parameter. If `properties.deployment.modelName` is missing for some reason, fall back to confirming the accepted ID by probing `POST {gateway-host}/models/openai/v1/chat/completions` with a tiny payload rather than guessing from the ARM `name`.

Match models to the user's use case based on the model name/description (e.g. a GPT-class model for chat, an embedding model for RAG). Suggest the best match as the default but let the user pick another.

### 2. Discover tools (MCP tool servers)

Tools are registered as **tool servers** in the gateway workspace. Each tool server is a federated MCP host exposed at a single MCP endpoint on the gateway. List them:

```
GET https://management.azure.com{gatewayResourceId}/workspaces/default/toolServers?api-version={apiVersion}
```

Each item's `name` is the tool server name. Build its MCP endpoint URL as `https://{gateway-host}/toolservers/{toolServerName}/mcp`. **`properties.mcpEndpointUrl` is frequently empty** in the ARM response, so do not rely on it — construct the URL from the host and tool server name, and only use `properties.mcpEndpointUrl` if it is non-empty. Filter to the tools relevant to the user's request (examine names and descriptions for keywords — e.g. for shipping, look for a "calculator" tool). Then **stop and ask the user**: "I found these tools for your use case. Which would you like to use?" List them clearly with brief descriptions and endpoints, and allow selecting all, some, or none.

> **Verify the tool server actually exposes tools before wiring it in.** A tool server can be registered but expose **zero** tools (e.g. a federated OpenAPI/MCP source that failed to sync). Confirm by doing a quick MCP handshake against the constructed URL — `POST` an `initialize` request, then a `tools/list` request, both with the `Api-Key` header and `Accept: application/json, text/event-stream`. If `tools/list` returns an empty array, tell the user that server has no usable tools right now (a gateway-side configuration issue, not a client bug) and let them pick a different one rather than scaffolding an agent that can't call anything.

### 3. Retrieve a credential

The model passthrough and MCP tool servers are called with a gateway **API key** — the **same key works for both**.

1. List the available keys (keys live at the gateway level, not the workspace):
   ```
   GET https://management.azure.com{gatewayResourceId}/apiKeys?api-version={apiVersion}
   ```
2. Pick a key (there is usually one named `default`).
3. Retrieve the secret:
   ```
   POST https://management.azure.com{gatewayResourceId}/apiKeys/{keyName}/listSecrets?api-version={apiVersion}
   ```
   The key is in `primaryKey`:
   ```json
   { "primaryKey": "2e41...", "secondaryKey": "365..." }
   ```

The credential is passed in the **`Api-Key`** header for both the model passthrough and the MCP tool servers.

> **Discovery-only path:** If the user only wants to explore and select assets (models/tools) and does **not** want to integrate them yet, you can stop here. Present the discovered assets and selected credential, and skip Part 2. Code generation is optional.

---

## Part 2 — Integrate into your application

By now you have (a) the selected model(s) and/or MCP tool server(s) and (b) the gateway API key. Now wire them into whatever the user is building.

**First, pick the integration path** — ask the user what they're building if it isn't already clear, then follow the matching path (they can combine A and B):

- **Path A — Call a model.** The user wants their app/script/service to send prompts to a model. Works from any language or raw HTTP via the gateway's OpenAI-compatible passthrough. _Most common for existing apps._
- **Path B — Connect MCP tools.** The user wants their app or MCP-capable client to call the gateway's registered MCP tool servers.
- **Path C — Scaffold a standalone agent.** The user wants a ready-to-run agent project (GitHub Copilot SDK) that combines models and tools.

Whichever path you take, integrate into the user's **existing** project when they have one (respect its language, framework, and conventions) rather than forcing a new scaffold. Path C's scaffold is only for users who explicitly want a fresh standalone agent.

**Shared rules (all paths):**

- Read every credential from environment variables (e.g. `AI_GATEWAY_API_KEY`) — never hardcode secrets. See _Shared: credentials & project hygiene_ below.
- The gateway authenticates **both** models and MCP tool servers with the same key, passed in the **`Api-Key`** request header.

---

### Path A — Call a model (OpenAI-compatible passthrough)

The AI Gateway exposes an **OpenAI-compatible** endpoint. Point any OpenAI-style client (or plain HTTP) at it:

- **Base URL:** `<ai-gateway-host>/models/openai/v1` — e.g. `https://my-gateway.westus2-01.ai.gateway-current.azure.com/models/openai/v1`. This is the same endpoint the AI Gateway Portal advertises to consumers; clients append `/chat/completions`.
- **Auth header:** `Api-Key: <gateway key>`. **Do not** rely on `Authorization: Bearer` — the gateway model passthrough rejects bearer-only auth with a misleading **`unknown_model`** error. If your client insists on an `api_key` field (many do), still set the `Api-Key` header explicitly.
- **Model identifier:** use the selected model's **`properties.deployment.modelName`** (e.g. `gpt-5.4-nano`) exactly — same dots, casing, and punctuation. **Never** use the ARM resource `name` (e.g. `gpt-5-4-nano`) or `displayName`; those return `unknown_model`.

#### curl

```bash
curl "$AI_GATEWAY_HOST/models/openai/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Api-Key: $AI_GATEWAY_API_KEY" \
  -d '{
    "model": "<properties.deployment.modelName>",
    "messages": [{ "role": "user", "content": "Hello!" }]
  }'
```

#### Python (openai SDK)

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=f"{os.environ['AI_GATEWAY_HOST']}/models/openai/v1",
    api_key=os.environ["AI_GATEWAY_API_KEY"],
    # The gateway authenticates via the Api-Key header, not Authorization: Bearer.
    default_headers={"Api-Key": os.environ["AI_GATEWAY_API_KEY"]},
)

resp = client.chat.completions.create(
    model="<properties.deployment.modelName>",  # e.g. "gpt-5.4-nano"
    messages=[{"role": "user", "content": "Hello!"}],
)
print(resp.choices[0].message.content)
```

#### TypeScript / JavaScript (openai SDK)

```ts
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: `${process.env.AI_GATEWAY_HOST}/models/openai/v1`,
  apiKey: process.env.AI_GATEWAY_API_KEY!,
  // The gateway authenticates via the Api-Key header, not Authorization: Bearer.
  defaultHeaders: { "Api-Key": process.env.AI_GATEWAY_API_KEY! },
});

const resp = await client.chat.completions.create({
  model: "<properties.deployment.modelName>", // e.g. "gpt-5.4-nano"
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(resp.choices[0].message.content);
```

> The passthrough is OpenAI-compatible, so streaming, tools/function-calling, and other OpenAI request fields work as usual — just keep the `Api-Key` header and the exact `modelName`.

---

### Path B — Connect to MCP tool servers

Each registered MCP tool server is reachable at its own MCP endpoint (captured during discovery), authenticated with the same gateway key via the **`Api-Key`** header. Use it from any MCP client:

- **Endpoint:** the tool server's MCP URL from discovery (e.g. `<ai-gateway-host>/toolservers/<name>/mcp`).
- **Transport:** streamable HTTP (`type: "http"`).
- **Auth header:** `Api-Key: <gateway key>`.

To sanity-check a tool server manually, run the MCP `initialize` + `tools/list` handshake:

```bash
curl "$TOOL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Api-Key: $AI_GATEWAY_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

To wire it into an application, configure your MCP client with the endpoint URL, `http` transport, and the `Api-Key` header — for example, in a client that reads an `mcp.json`/`mcpServers` map:

```json
{
  "mcpServers": {
    "<tool-name>": {
      "type": "http",
      "url": "<tool-endpoint>",
      "headers": { "Api-Key": "${AI_GATEWAY_API_KEY}" }
    }
  }
}
```

Adapt the exact shape to whatever MCP client/library the user's app uses (the essentials are always: endpoint URL, HTTP transport, and the `Api-Key` header). If the user is building an agent that needs these tools, prefer **Path C**, which wires models and MCP tools together.

---

### Path C — Scaffold a standalone agent (GitHub Copilot SDK)

Use this path when the user explicitly wants a runnable standalone **agent** project that combines the selected model and MCP tools.

#### C.1 Choose language

Ask the user which language they prefer. **Default to Python** if not specified. Supported:

- Python (default)
- TypeScript/JavaScript

#### C.2 Generate agent code

Generate the agent code using the **GitHub Copilot SDK** (code, docs, examples: https://github.com/github/copilot-sdk).

> **Required SDK version: `github-copilot-sdk >= 1.0.0`.** The agent authenticates the BYOK model and the MCP tool servers by passing the gateway key in custom request headers (`Api-Key`). SDK versions older than 1.0.0 silently drop provider/custom headers, so the gateway rejects the call with a misleading `unknown_model` error. Always pin `>= 1.0.0` in `requirements.txt` / `package.json` and in any install command.

The generated code must:

- Use the GitHub Copilot SDK correctly for the chosen language (default to Python, unless the user specifies otherwise). Require **`github-copilot-sdk >= 1.0.0`** — older versions drop the custom headers used to authenticate the gateway model and tools
- Configure MCP tool connections to the selected AI Gateway tool servers via `mcp_servers` in the session config, using `type: "http"` with the tool server's MCP endpoint URL
- Authenticate tool servers with the gateway API key passed in the **`Api-Key`** header via the `headers` config
- Configure model access through a BYOK `provider` in the session config
- Authenticate models with the **same** gateway API key passed in the **`Api-Key`** header via the provider's `headers` config — **not** the `api_key` field alone. The SDK sends `api_key` as an `Authorization: Bearer` header, which the AI Gateway model passthrough rejects with a misleading **`unknown_model`** error. Set the `Api-Key` header explicitly (keep `api_key` too, since the SDK requires a non-empty value)
- Use model provider `type: "openai"` (the AI Gateway exposes an OpenAI-compatible passthrough, where the model is selected by name in the request body)
- Construct the model `base_url` as the AI Gateway's unified model passthrough: `<ai-gateway-host>/models/openai/v1` — for example `https://my-gateway.westus2-01.ai.gateway-current.azure.com/models/openai/v1`. This is the same endpoint the AI Gateway Portal advertises to consumers (the SDK appends `/chat/completions`)
- Precisely specify the model parameter and match it exactly to the selected model's **`properties.deployment.modelName`** (e.g. `gpt-5.4-nano`) — same dots, same casing, same punctuation. Never use the ARM resource `name` (e.g. `gpt-5-4-nano`) or `displayName`; those are rejected with `unknown_model`
- Include `"on_permission_request": PermissionHandler.approve_all` in the session config (import `PermissionHandler` from `copilot`)
- Pass the session config to `create_session` as keyword arguments (e.g. `create_session(model=..., provider=..., mcp_servers=...)`), like in the example below
- Read all credentials from environment variables — never hardcode secrets
- Load environment variables from a `.env` file using `python-dotenv` (Python) or `dotenv` (TypeScript)
- Use `send_and_wait()` with the prompt as a positional string to get the agent's response, then **always print the response content or the error** — the user must see output
- Handle errors gracefully with full tracebacks for debugging
- Include a clear main entry point and example usage
- Match the code example below as closely as possible

##### Python Example Structure

```python
import asyncio
import os
from dotenv import load_dotenv
from copilot import CopilotClient, PermissionHandler

load_dotenv()

async def main():
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model="<selected-model>",  # e.g. "gpt-4o"
            # BYOK provider — points to the AI Gateway unified model passthrough.
            # The gateway authenticates the model passthrough via the `Api-Key`
            # header, so pass the key in `headers`. The `api_key` field alone is
            # sent as `Authorization: Bearer`, which the gateway rejects with
            # `unknown_model`.
            provider={
                "type": "openai",
                "base_url": "<ai-gateway-host>/models/openai/v1",
                "api_key": os.environ["AI_GATEWAY_API_KEY"],
                "headers": {
                    "Api-Key": os.environ["AI_GATEWAY_API_KEY"],
                },
            },
            # MCP tool servers from AI Gateway
            mcp_servers={
                "<tool-name>": {
                    "type": "http",
                    "url": "<tool-endpoint>",
                    "headers": {
                        "Api-Key": os.environ["AI_GATEWAY_API_KEY"],
                    },
                    "tools": ["*"],
                },
                # Add more tools as needed
            },
        )

        def on_event(event):
            event_type = event.type.value
            if event_type == "tool.execution_start":
                print(f"  [tool call: {event.data.tool_name}]")
            elif event_type == "error":
                msg = getattr(event.data, "message", str(event))
                print(f"  [error: {msg}]")

        session.on(on_event)

        reply = await session.send_and_wait("<user prompt>")

        if reply:
            print("\n=== Agent Response ===")
            print(reply.data.content if reply.data.content else "(empty response)")
        else:
            print("\n=== No response received from agent ===")

        await session.disconnect()

    except Exception as e:
        print(f"\nFailed to run agent: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

#### C.3 Create project files

After generating the agent code, create a complete, self-contained project the user can download and run as-is. See _Shared: credentials & project hygiene_ below for `.env`, `.env.example`, and `.gitignore`, plus:

4. **`requirements.txt`** (Python) — pin the agent's dependencies so the project installs in one command:

   ```
   github-copilot-sdk>=1.0.0
   python-dotenv
   ```

   (For TypeScript, generate a `package.json` with the equivalent dependencies — `github-copilot-sdk` at `>=1.0.0` — and a `start` script.)

5. **`README.md`** — a short, self-contained guide so the downloaded project runs without this chat. Include:
   - what the agent does and which gateway model + tool servers it uses (by name)
   - prerequisites (Python 3.10+, the Copilot CLI, `github-copilot-sdk >= 1.0.0`)
   - install steps (`pip install -r requirements.txt`)
   - how to set credentials (copy `.env.example` to `.env`, or use the pre-filled `.env`)
   - the run command and the expected output

#### C.4 Provide setup instructions

After generating the code, provide:

- Required package installation commands: `pip install "github-copilot-sdk>=1.0.0" python-dotenv` (the `>= 1.0.0` pin is mandatory — older SDKs drop the custom `Api-Key` headers and the gateway returns `unknown_model`)
- Copilot CLI must be installed separately (the SDK communicates with it via JSON-RPC)
- Environment variable setup:
  - `AI_GATEWAY_API_KEY` — the gateway API key from discovery (passed via the `Api-Key` header for tool servers and via the BYOK provider `api_key` for the model)
- How to run the agent

#### C.5 Run and verify

Don't stop at "here's the code." Run the agent once and confirm the wiring actually works, then report the outcome to the user:

- **Run it** (e.g. `python agent.py`) and read the output.
- **Distinguish config failures from benign backend conditions.** Treat these as a **healthy** end-to-end wiring (the gateway accepted the request) — report success and move on:
  - `429 ... exceeded rate limit` or quota errors from the model
  - empty/slow responses caused by the upstream model, not the client
- **Treat these as real bugs to fix before handing off:**
  - `unknown_model` → wrong model identifier (used ARM `name`/`displayName` instead of `properties.deployment.modelName`) **or** an SDK older than `1.0.0` dropping the `Api-Key` header
  - `KeyError: 'AI_GATEWAY_API_KEY'` → `.env` not loaded, usually a BOM (see the `.env` note below)
  - `401`/`403` → wrong or missing `Api-Key` header
- If you can't get a clean model response because of a backend `429`/quota, say so explicitly and note that everything up to the model was validated, rather than implying the full round-trip succeeded.

---

### Shared: credentials & project hygiene

Whenever you write credentials or scaffold files into the user's project (any path), keep secrets safe:

1. **`.env`** — populated with the actual key retrieved during discovery:

   ```
   AI_GATEWAY_API_KEY=<actual gateway API key from discovery>
   ```

   > **Security note:** this writes a **live gateway secret in cleartext** to disk. The `.gitignore` (below) keeps it out of source control, but warn the user that the file holds a real key and to **rotate it in the AI Gateway Portal if it is ever exposed or shared**.

   > **Write `.env` as UTF-8 _without_ a BOM.** `python-dotenv` (and `dotenv` for Node) does **not** strip a leading byte-order mark, so a BOM makes the first variable load as `\ufeffAI_GATEWAY_API_KEY` and the app crashes with `KeyError: 'AI_GATEWAY_API_KEY'`. This bites on Windows specifically: PowerShell's `Set-Content -Encoding utf8` and `Out-File` **add a BOM**. Write the file with a BOM-free encoder instead, e.g.:
   >
   > ```powershell
   > [System.IO.File]::WriteAllText("$PWD\.env", "AI_GATEWAY_API_KEY=$key`n", (New-Object System.Text.UTF8Encoding($false)))
   > ```
   >
   > or simply create the file through your editor/agent file-write tool, which does not add a BOM. After writing, sanity-check that the first byte is not `0xEF`.

2. **`.env.example`** — a template with a placeholder value for documentation:

   ```
   AI_GATEWAY_API_KEY=your-gateway-api-key-here
   ```

3. **`.gitignore`** — must include `.env` to prevent committing secrets:

   ```
   .env
   __pycache__/
   *.pyc
   .venv/
   ```
