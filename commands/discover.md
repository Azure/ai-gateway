---
description: Discover the models and MCP tool servers registered in an AI Gateway and summarize which ones fit your use case.
argument-hint: [gateway resource id or host]
---

# /ai-gateway:discover

Discover — and only discover — the AI assets registered in an AI Gateway. This is a
**read-only** exploration command: it lists models and MCP tool servers and helps the
user pick the ones that match their intent. It never provisions, updates, or deletes
anything, and it does **not** scaffold code (use `/ai-gateway:build` for that).

Follow the discovery workflow defined in the bundled skill
`skills/use-ai-gateway/SKILL.md` — specifically **Part 1 — Discover & select assets**:

1. Determine the target gateway from `$ARGUMENTS` if provided (an ARM
   `gatewayResourceId` or a gateway host). If it is missing or ambiguous, ask the user
   for it before making any call.
2. List the **models** in the gateway workspace and read each model's
   `properties.deployment.modelName` (the exact identifier accepted by the OpenAI
   passthrough — never the ARM `name` or `displayName`).
3. List the **MCP tool servers**, build each MCP endpoint URL as
   `https://{gateway-host}/toolservers/{toolServerName}/mcp`, and verify each server
   actually exposes tools via a quick `initialize` + `tools/list` MCP handshake.
4. Present a clear, grouped summary: models (id + description) and tool servers
   (name + endpoint + tool count), highlighting the best matches for the user's stated
   use case. Then ask which assets they want to use.

Stop after presenting the assets. Do not retrieve credentials or generate code unless
the user explicitly asks to continue (or runs `/ai-gateway:build`).
