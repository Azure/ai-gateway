"""A Foundry hosted agent whose model calls and MCP tool calls both go through AI Gateway.

The agent has no Foundry model deployment and no direct route to a tool. It calls the gateway's
OpenAI-compatible model endpoint with an alias, and the gateway's MCP endpoint for one MCP server,
both with its own gateway API key.

Run it locally with `azd ai agent run`, which reads the values from the azd environment. To run it without azd,
copy .env.example to .env, install requirements.txt in a virtual environment, and run `python main.py`.
"""

import asyncio
import os

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from dotenv import load_dotenv

load_dotenv()

INSTRUCTIONS = """
You answer questions about Microsoft and Azure technologies.
- Search the Microsoft Learn tools before you answer, and cite the URLs you used.
- If the tools don't cover the question, say so instead of guessing.
- Keep answers under 150 words.
"""


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Set {name}. With azd, run: azd env set {name} <value>")
    return value


async def main() -> None:
    gateway_url = required("AI_GATEWAY_URL").rstrip("/")
    api_key = required("AI_GATEWAY_API_KEY")
    model = required("AI_GATEWAY_MODEL")
    mcp_server = os.environ.get("AI_GATEWAY_MCP_SERVER", "").strip() or "learn"

    # The model endpoint accepts the key as the SDK's bearer token. Don't add an api-key header too:
    # the gateway rejects a request that has both.
    client = OpenAIChatClient(
        model=model,
        base_url=f"{gateway_url}/default/models/openai/v1/",
        api_key=api_key,
    )

    # The MCP endpoint takes the key only in the api-key header.
    tools = MCPStreamableHTTPTool(
        name="gateway-tools",
        url=f"{gateway_url}/default/toolservers/{mcp_server}/mcp",
        static_headers={"api-key": api_key},
        approval_mode="never_require",
        load_prompts=False,
        request_timeout=60,
    )

    async with Agent(
        client=client,
        name="gateway-docs-agent",
        instructions=INSTRUCTIONS,
        tools=tools,
        # Foundry keeps the conversation history, so the model call doesn't need to store it.
        default_options={"store": False},
    ) as agent:
        await ResponsesHostServer(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())
