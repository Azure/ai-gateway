// Calls a model through AI Gateway with the OpenAI npm package: once with the Responses API and once with
// Chat Completions. The gateway authenticates the api-key header, so the SDK's own API key is a placeholder.
//
// Usage (Node.js 22.18 or later runs TypeScript directly; on older versions use `npx tsx first-call.ts`):
//   npm install
//   export AI_GATEWAY_URL="https://<gateway>.azure-api.net"
//   export AI_GATEWAY_MODEL="<model-alias>"
//   export AI_GATEWAY_API_KEY="..."      // never commit this value
//   node first-call.ts
import OpenAI from "openai";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} before running this sample.`);
  return value;
}

const gatewayUrl: string = required("AI_GATEWAY_URL").replace(/\/+$/, "");
const model: string = required("AI_GATEWAY_MODEL");

const client = new OpenAI({
  baseURL: `${gatewayUrl}/default/models/openai/v1`,
  apiKey: "unused",
  defaultHeaders: { "api-key": required("AI_GATEWAY_API_KEY") },
});

const response = await client.responses.create({
  model,
  input: "Write a one-sentence status update.",
});
console.log(`Responses API:    ${response.output_text}`);

const completion = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Describe an AI gateway in one sentence." }],
});
console.log(`Chat Completions: ${completion.choices[0].message.content}`);
console.log(`Tokens used:      ${completion.usage?.total_tokens ?? "n/a"}`);
