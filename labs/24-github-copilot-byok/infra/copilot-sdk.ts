// Runs a GitHub Copilot SDK agent session on gpt-6-astra published by Azure AI Gateway (bring your own key).
// Set AI_GATEWAY_URL and AI_GATEWAY_API_KEY first. No GitHub sign-in is needed: every model call goes to the gateway.
import { CopilotClient, approveAll } from "@github/copilot-sdk";

const gatewayUrl = process.env.AI_GATEWAY_URL?.replace(/\/$/, "");
const apiKey = process.env.AI_GATEWAY_API_KEY;
const model = process.env.AI_GATEWAY_MODEL ?? "gpt-6-astra";
if (!gatewayUrl || !apiKey) {
  throw new Error("Set AI_GATEWAY_URL and AI_GATEWAY_API_KEY first.");
}

const client = new CopilotClient();
try {
  const session = await client.createSession({
    model,
    provider: {
      type: "openai",
      baseUrl: `${gatewayUrl}/default/models/openai/v1`,
      apiKey,
      wireApi: "responses",
    },
    onPermissionRequest: approveAll,
  });

  const prompt = process.argv.slice(2).join(" ") || "Which model are you? Then list the files in this folder.";
  const reply = await session.sendAndWait({ prompt });
  console.log(reply?.data.content);
  await session.disconnect();
} finally {
  await client.stop();
}
