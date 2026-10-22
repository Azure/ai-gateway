---
title: Stream responses and count every token
summary: Stream Chat Completions and Responses API replies through the gateway, read the server-sent events that your client receives, and prove that a token limit counts streamed tokens even when the client never asks for usage.
category: models
level: Intermediate
duration: 20
tracks: [cli, code, portal, iac]
order: 3.7
status: new
illustration: diagrams/streaming-usage.svg
tags: [streaming, SSE, server-sent events, stream_options, include_usage, usage, tokenLimit, Responses API, time to first token]
objectives:
  - Read the server-sent events that a streamed Chat Completions response returns through the gateway
  - Get token usage at the end of a stream with include_usage, and skip chunks that have no choices
  - Stream the Responses API and read usage from the response.completed event
  - Prove that a token limit counts streamed tokens whether or not the client asks for usage
prereqs:
  - 02-first-model-call
---

# Stream responses and count every token

Chat apps and agents stream their replies: the model sends text a few tokens at a time, so people start reading
after a second or two instead of waiting for the whole answer. Streaming used to be a blind spot for governance,
because a streamed Chat Completions response only reports token usage when the client asks for it. In this lab you
stream through the gateway with curl, PowerShell, and the OpenAI SDKs, read every event the client receives, and
then prove that a token limit still counts every streamed token.

![A streamed request passes the gateway's limits before the stream starts, and the gateway captures usage while the stream flows back to the client](../assets/diagrams/streaming-usage.svg "Token and cost limits are checked before the stream starts. While the stream flows back, the gateway records its token usage for limits, budgets, and Monitoring.")

<!-- widget: stream-usage -->

## Before you begin

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need a gateway, an imported
  model, a callable alias, and a runtime API key from **Access** › **Keys**.
- For the shell steps: `curl` and `jq` for Bash, or PowerShell 7.4 or later. For the CLI and IaC tracks: the
  [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with `az login`.
- For the Code track: Python 3.10 or later, or Node.js 22.18 or later.
- Permission to change the gateway, for example **Contributor** on the resource group, for the token limit steps.

Set these variables once, from the lab folder (`labs/23-streaming-responses`). Every track and the **Verify**
section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"                 # 24 characters or fewer
export PROVIDER="<provider-name>"          # for example foundry-models
export MODEL="<model-name>"                # the backend model name under that provider
export STREAM_ALIAS="$MODEL-stream"        # the token-limited alias that this lab creates

export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(az resource show -g "$RG" -n "$GATEWAY" --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv)"
export GW="https://management.azure.com$GATEWAY_ID"
export WS="$GW/workspaces/default"
export MODEL_URL="$WS/modelProviders/$PROVIDER/models/$MODEL"
export AI_GATEWAY_URL="https://$(az resource show --ids "$GATEWAY_ID" --query properties.frontend.defaultHostname -o tsv)"
# A starting guess for the alias. Confirm it on the model's Aliases tab (lab 02) and replace it if it differs.
export AI_GATEWAY_MODEL="$(az rest --url "$MODEL_URL?$API" --query properties.deployment.modelName -o tsv)"
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG           = "<resource-group>"
$GATEWAY      = "<gateway>"                 # 24 characters or fewer
$PROVIDER     = "<provider-name>"           # for example foundry-models
$MODEL        = "<model-name>"              # the backend model name under that provider
$STREAM_ALIAS = "$MODEL-stream"             # the token-limited alias that this lab creates

$API        = "api-version=2025-09-01-preview"
$GATEWAY_ID = az resource show -g $RG -n $GATEWAY --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv
$GW         = "https://management.azure.com$GATEWAY_ID"
$WS         = "$GW/workspaces/default"
$MODEL_URL  = "$WS/modelProviders/$PROVIDER/models/$MODEL"
$env:AI_GATEWAY_URL = "https://$(az resource show --ids $GATEWAY_ID --query properties.frontend.defaultHostname -o tsv)"
# A starting guess for the alias. Confirm it on the model's Aliases tab (lab 02) and replace it if it differs.
$env:AI_GATEWAY_MODEL = az rest --url "$MODEL_URL`?$API" --query properties.deployment.modelName -o tsv
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

> [!TIP]
> The Code track only needs `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL`, and `AI_GATEWAY_API_KEY`. If you skip the token
> limit steps, you can set those three by hand and skip the Azure CLI.

## How it works

Add `"stream": true` to a Chat Completions request and the gateway answers with `Content-Type:
text/event-stream`. The body is a series of server-sent events (SSE): each one is a `data:` line with a JSON chunk,
followed by a blank line. The gateway passes each chunk on as the model produces it, and the response carries
`x-accel-buffering: no`, which tells proxies such as NGINX not to hold it back.

This is what a streamed reply from a Foundry model looks like through the gateway:

| Chunk | `choices` | What it carries |
|---|---|---|
| Prompt filter results | Empty `[]` | Content safety results for the prompt. `id` and `model` are empty strings. |
| Role | One choice | `delta.role` is `assistant` and `delta.content` is an empty string. |
| Content deltas | One choice | `delta.content` holds the next few characters of the reply. `usage` is `null`. |
| Finish | One choice | `finish_reason` is `stop`, or `length` when the reply hits `max_completion_tokens`. |
| Usage | Empty `[]` | `usage` with `prompt_tokens`, `completion_tokens`, and `total_tokens`. Sent when the client sets `stream_options.include_usage`. |
| `data: [DONE]` | Not JSON | The end of the stream. Stop reading. |

Two chunks have an empty `choices` array, so code that reads `choices[0]` on every chunk crashes on the first one.

**Where the gateway counts tokens.** A token limit or cost limit is checked **before** the gateway forwards the
request. When a counter is exhausted, the client gets an ordinary JSON error, such as `429` with `Retry-After`, and no
stream starts. Once a stream starts, it runs to the end, even if it takes the counter past the limit; the next request
is throttled. While the stream flows, the gateway records its token usage for token limits, cost limits, and
Monitoring.

**Usage without `include_usage`.** Since the [September 24, 2026 release](https://ai.gateway.azure.com/docs/releases/2026-09-24),
the gateway makes sure it has a usage record for every streamed Chat Completions response, even when the client
doesn't set `stream_options.include_usage`, so the counters stay accurate. The release notes ask clients that parse
the events themselves to accept a usage-only chunk before `[DONE]`, even when they didn't ask for one. In our test
run in October 2026, a client that didn't set `include_usage` received no usage chunk, yet the token limit counted its
tokens exactly as it did for a client that asked. So write your client to work either way: skip chunks with an empty
`choices` array, and take usage from whichever chunk carries it.

The Responses API streams typed events instead: each `data:` line follows an `event:` line, and the last event,
`response.completed`, always carries the usage.

## Stream a response

Pick a track. Both stream the same request through the gateway and show the text as it arrives, the events, and
the usage.

<!-- track: cli | curl and PowerShell -->

### Watch the raw events

curl buffers its output by default; `-N` turns that off, so each event prints the moment it arrives. PowerShell's
`Invoke-RestMethod` and `Invoke-WebRequest` wait for the whole body, so the PowerShell script reads the stream
with `HttpClient`.

```bash title="Bash"
curl -sSN "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in five words.\"}]}"
```

```powershell title="PowerShell"
./infra/stream-chat.ps1 -Raw -Prompt "Say hello in five words."
```

Expected output (shortened; your text and IDs differ):

```text
data: {"choices":[],"created":0,"id":"","model":"","object":"","prompt_filter_results":[{"prompt_index":0,"content_filter_results":{…}}]}

data: {"choices":[{"delta":{"content":"","refusal":null,"role":"assistant"},"finish_reason":null,"index":0,…}],"model":"gpt-6-luna-2026-09-22","object":"chat.completion.chunk",…,"usage":null}

data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null,"index":0,…}],…,"usage":null}

data: {"choices":[{"delta":{"content":" there"},"finish_reason":null,"index":0,…}],…,"usage":null}

…

data: {"choices":[{"delta":{},"finish_reason":"stop","index":0,…}],…,"usage":null}

data: [DONE]
```

### Stream with the script

The script prints the reply as it streams, then counts the events, measures the time to the first token, and shows
the usage chunk if the stream had one.

<!-- include: infra/stream-chat.sh -->

```bash title="Bash"
./infra/stream-chat.sh
```

```powershell title="PowerShell"
./infra/stream-chat.ps1
```

On GitHub, open [stream-chat.sh](infra/stream-chat.sh) or [stream-chat.ps1](infra/stream-chat.ps1).

Expected output (your text and numbers differ):

```text
Streaming shows replies as they're generated, so users see progress right away. They can start reading before the full answer is ready. That makes the app feel more responsive than waiting for one complete message.

Events              43 (1 with an empty choices array)
First token         1.77 s
Usage chunk         none: run again with --usage to ask for one
HTTP status         200
Content-Type        text/event-stream; charset=utf-8
Served by           gpt-6-luna-2026-09-22
```

### Ask for usage at the end of the stream

Run the script again with the option that sets `"stream_options": {"include_usage": true}`:

```bash title="Bash"
./infra/stream-chat.sh --usage
```

```powershell title="PowerShell"
./infra/stream-chat.ps1 -Usage
```

Expected output:

```text
Streaming shows the reply as it's generated instead of waiting for the whole answer. You can start reading right away. That makes the app feel more responsive.

Events              35 (2 with an empty choices array)
First token         1.74 s
Usage chunk         prompt 19, completion 34, total 53
HTTP status         200
Content-Type        text/event-stream; charset=utf-8
Served by           gpt-6-luna-2026-09-22
```

The second empty-`choices` chunk is the usage chunk, the last one before `[DONE]`. `stream_options` is only valid
together with `"stream": true`; without it, the gateway returns `400`.

### Stream the Responses API

The Responses API names every event. List the event types in order, then read the usage from `response.completed`:

```bash title="Bash"
curl -sSN "${AI_GATEWAY_URL%/}/default/models/openai/v1/responses" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"stream\":true,\"input\":\"Say hello in five words.\"}" > events.txt
grep '^event:' events.txt | uniq -c
sed -n 's/^data: {/{/p' events.txt | jq -c 'select(.type == "response.completed") | .response.usage'
rm events.txt
```

```powershell title="PowerShell"
$body = @{ model = $env:AI_GATEWAY_MODEL; stream = $true; input = "Say hello in five words." } | ConvertTo-Json
$r = Invoke-WebRequest -Method Post -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/responses" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
$lines = $r.Content -split "`n"
$prev = $null; $n = 0
foreach ($e in $lines -match '^event:') { if ($e -eq $prev) { $n++ } else { if ($prev) { '{0,4} {1}' -f $n, $prev }; $prev = $e; $n = 1 } }
'{0,4} {1}' -f $n, $prev
($lines -match '^data: \{' | ForEach-Object { $_.Substring(6) | ConvertFrom-Json } |
  Where-Object type -eq 'response.completed').response.usage | ConvertTo-Json -Compress
```

Expected output (your counts differ):

```text
   1 event: response.created
   1 event: response.in_progress
   1 event: response.output_item.added
   1 event: response.output_item.done
   1 event: response.output_item.added
   1 event: response.content_part.added
   7 event: response.output_text.delta
   1 event: response.output_text.done
   1 event: response.content_part.done
   1 event: response.output_item.done
   1 event: response.completed
{"input_tokens":12,"input_tokens_details":{"cache_write_tokens":0,"cached_tokens":0},"output_tokens":66,"output_tokens_details":{"reasoning_tokens":53},"total_tokens":78}
```

The first `output_item` pair is the model's reasoning item; the second is the message that carries the text. The
`reasoning_tokens` count shows why the first token can take a moment with a reasoning model.

<!-- track: code | Code -->

### Install the SDK

Each sample reads `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL`, and `AI_GATEWAY_API_KEY` from the environment. Run the
commands from the lab folder.

```bash title="Python"
cd infra
pip install -r requirements.txt     # the openai package
```

```bash title="TypeScript"
cd infra
npm install                         # the openai npm package
```

### Stream from code

Pass `stream=True` and iterate over the chunks. Skip chunks without `choices`, and keep the usage from the chunk that
has it.

```python title="Python"
stream = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Explain in two sentences why streaming makes chat apps feel faster."}],
    stream=True,
    stream_options={"include_usage": True},
)
usage = None
for chunk in stream:
    if chunk.usage:
        usage = chunk.usage
    if not chunk.choices:  # the prompt filter chunk and the usage chunk
        continue
    print(chunk.choices[0].delta.content or "", end="", flush=True)
print(f"\nTokens used: {usage.total_tokens if usage else 'no usage chunk'}")
```

```typescript title="TypeScript"
const stream = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Explain in two sentences why streaming makes chat apps feel faster." }],
  stream: true,
  stream_options: { include_usage: true },
});
let usage: OpenAI.CompletionUsage | undefined;
for await (const chunk of stream) {
  if (chunk.usage) usage = chunk.usage;
  // choices[0] is undefined on the prompt filter chunk and the usage chunk.
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}
console.log(`\nTokens used: ${usage?.total_tokens ?? "no usage chunk"}`);
```

The Responses API streams typed events. Print `response.output_text.delta` events and read the usage from
`response.completed`:

```python title="Python"
for event in client.responses.create(model=model, input="Write a one-sentence status update.", stream=True):
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
    elif event.type == "response.completed":
        print(f"\nTokens used: {event.response.usage.total_tokens}")
```

```typescript title="TypeScript"
const events = await client.responses.create({ model, input: "Write a one-sentence status update.", stream: true });
for await (const event of events) {
  if (event.type === "response.output_text.delta") process.stdout.write(event.delta);
  else if (event.type === "response.completed") console.log(`\nTokens used: ${event.response.usage?.total_tokens}`);
}
```

The full samples create the client, time the first token, and print both streams: open [stream.py](infra/stream.py)
and [stream.ts](infra/stream.ts).

### Run the sample

```bash title="Python"
python stream.py
```

```bash title="TypeScript"
node stream.ts      # Node.js 22.18 or later; on older versions run: npx tsx stream.ts
```

Expected output (your text differs):

```text
Chat Completions:
Streaming shows each response as it's generated instead of making you wait for the whole message, so you see progress right away. It also lets you start reading or reacting before the response is complete.
First token:      1.77 s
Tokens used:      74 (prompt 18, completion 56)

Responses API:
Streaming is running smoothly, with no interruptions reported.
Tokens used:      66 (input 16, output 50)
```

<!-- /tracks -->

> **Checkpoint**
> The reply appears a few words at a time, and you can name the chunk that carries the usage in each API.

## Put a token limit on a streaming alias

To find out whether the gateway counts streamed tokens, give a new alias, `<model-name>-stream`, a deliberately low
limit: **1,000 tokens per minute for each caller identity**. It targets the same backend model as your alias from
lab 02, so clients that call that alias aren't affected.

<!-- track: portal | Portal -->

### Create the alias

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top bar.
2. Select **Models** › **Aliases** › **Add alias**.
3. On **Basics**, set **Alias name** to `<model-name>-stream`, for example `gpt-6-luna-stream`. Select **Next**.
4. On **Select models**, select your model in **Available backend models**. Select **Next**.
5. Keep the defaults on **Priority and weights**, select **Next**, then select **Create** on **Review**.

### Add the token limit

1. Select **Policies** › **Add policy**. On the **Type** step, under **Cost & Rate Limits**, select
   **Token rate limit**, then **Next**.
2. On the **Scope** step, select **Individual assets**, select the `<model-name>-stream` alias, then **Next**.
3. On the **Details** step, set **Time period** to **Per minute**, **Allowed tokens** to `1000`, and
   **Counter dimensions** to **Caller identity**. Select **Create**.

![The Add policy wizard on the Type step](../assets/screens/policy-add-wizard.png "Policies › Add policy opens a three-step wizard: Type, Scope, Configure.")

> **Checkpoint**
> **Models** › **Aliases** lists `<model-name>-stream`, and **Policies** lists a **Token rate limit** of 1,000
> tokens per minute scoped to it.

<!-- track: cli | Azure CLI -->

### Create the alias with its token limit

An alias carries its own `policies` array, so one `PUT` creates the alias and its limit together.

```bash title="Bash"
az rest --method put --url "$WS/aliases/$STREAM_ALIAS?$API" \
  --body "$(jq -cn --arg m "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$MODEL" '{properties: {
      description: "Streaming lab: 1,000 tokens per minute for each caller",
      backendModels: [{resourceId: $m}],
      policies: [{type: "tokenLimit", count: 1000, period: "minute", counterKey: ["identity"]}]}}')" \
  --query "{alias:name, policies:properties.policies}" -o json
```

```powershell title="PowerShell"
@{ properties = @{
    description   = "Streaming lab: 1,000 tokens per minute for each caller"
    backendModels = @(@{ resourceId = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$MODEL" })
    policies      = @(@{ type = "tokenLimit"; count = 1000; period = "minute"; counterKey = @("identity") })
  } } | ConvertTo-Json -Depth 10 -Compress | Set-Content body.json
az rest --method put --url "$WS/aliases/$STREAM_ALIAS`?$API" --body "@body.json" `
  --query "{alias:name, policies:properties.policies}" -o json
Remove-Item body.json
```

> **Checkpoint**
> The output shows your alias and one policy with `"type": "tokenLimit"`, `"count": 1000`, `"period": "minute"`,
> `"counterKey": ["identity"]`, and `"scope": "resource"`.

<!-- track: iac | Bicep -->

### Deploy the template from lab 06

[Throttle tokens per caller with token limits](../06-token-limits/README.md) ships a template that publishes a
token-limited alias for an existing model. Reuse it with the streaming alias name.

```bash title="Bash"
az deployment group create -g "$RG" -n 23-streaming-alias \
  --template-file ../06-token-limits/infra/main.bicep \
  --parameters gatewayName="$GATEWAY" providerName="$PROVIDER" modelName="$MODEL" aliasName="$STREAM_ALIAS" \
               allowedTokens=1000 period=minute counterKey="['identity']" \
  --query properties.outputs
```

```powershell title="PowerShell"
az deployment group create -g $RG -n 23-streaming-alias `
  --template-file ../06-token-limits/infra/main.bicep `
  --parameters gatewayName=$GATEWAY providerName=$PROVIDER modelName=$MODEL aliasName=$STREAM_ALIAS `
               allowedTokens=1000 period=minute counterKey="['identity']" `
  --query properties.outputs
```

On GitHub, open [main.bicep](../06-token-limits/infra/main.bicep).

> **Checkpoint**
> The outputs show `aliasName` set to your streaming alias, and **Policies** in the portal lists a
> **Token rate limit** scoped to it.

<!-- /tracks -->

## Verify

Send bursts of streamed requests that each use about 220 tokens: first without asking for usage, then with it. If the
gateway only counted the tokens that clients report, the first burst would never be throttled.

<!-- steps -->

### Stream a burst without asking for usage

For each request, the script prints the status, `Retry-After`, the number of events, and the usage chunk, if any.

```bash title="Bash"
./infra/stream-burst.sh "$STREAM_ALIAS" 8
```

```powershell title="PowerShell"
./infra/stream-burst.ps1 -Model $STREAM_ALIAS -Requests 8
```

On GitHub, open [stream-burst.sh](infra/stream-burst.sh) or [stream-burst.ps1](infra/stream-burst.ps1).

Expected output (your counts differ):

```text
Request  Status  Retry-After  Events  Usage chunk
1        200     -            209     none
2        200     -            187     none
3        200     -            207     none
4        200     -            200     none
5        200     -            196     none
6        200     -            191     none
7        429     2            -       Token limit is exceeded. Try again in 2 seconds.
8        429     1            -       Token limit is exceeded. Try again in 1 seconds.
```

No stream carried a usage chunk, yet the gateway throttled request 7, after about 1,300 tokens. If it had
counted only the prompts, about 25 tokens each, the alias would have allowed roughly 40 requests.

> [!NOTE]
> A new alias or policy can take up to a minute to apply, and the counters catch up within a few seconds, so a fast
> burst can go a few hundred tokens past the limit. If every request returns `200`, wait a minute and run it again.

### Stream a burst with usage

Wait a minute for the window to reset, then run the same burst with `include_usage`:

```bash title="Bash"
sleep 60
./infra/stream-burst.sh --usage "$STREAM_ALIAS" 8
```

```powershell title="PowerShell"
Start-Sleep 60
./infra/stream-burst.ps1 -Model $STREAM_ALIAS -Requests 8 -Usage
```

Expected output:

```text
Request  Status  Retry-After  Events  Usage chunk
1        200     -            196     218 tokens
2        200     -            186     208 tokens
3        200     -            196     218 tokens
4        200     -            191     213 tokens
5        200     -            211     233 tokens
6        200     -            191     213 tokens
7        429     1            -       Token limit is exceeded. Try again in 1 seconds.
8        200     -            193     215 tokens
```

The throttle point is the same: the gateway counted the streams the same way whether or not the client asked for
usage. Request 8 succeeds again because it was sent after the `Retry-After` wait.

### Inspect a throttled streaming request

Run the burst once more and, while the alias is throttled, look at a full response:

```bash
curl -sS -i "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$STREAM_ALIAS\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}"
```

Expected output, when the limit is active:

```text
HTTP/2 429
content-type: application/json
retry-after: 3
content-length: 84

{ "statusCode": 429, "message": "Token limit is exceeded. Try again in 3 seconds." }
```

The throttled answer is plain JSON, not an event stream, because the gateway refused the request before it reached
the model. Check the status code before you start reading events, and honor `Retry-After`.

### Find the streamed calls in Monitoring

If you configured Application Insights in [Monitor usage, cost, and traces](../13-monitoring/README.md), open
**Monitoring**. The streamed requests show their token counts next to the non-streamed ones, and the throttled
requests appear as `429` outcomes.

<!-- /steps -->

> **Checkpoint**
> Both bursts were throttled at the same request, the burst without `include_usage` included, and the throttled
> request returned a JSON `429` with `Retry-After` instead of a stream.

## Go further

- **Cap spend for streams.** A cost limit is estimated from the same usage record, so streamed calls count against
  budgets too. Try it in [Enforce cost budgets](../07-cost-budgets/README.md).
- **Shorten the time to the first token.** Reasoning models think before they write. For chat that needs a quick
  first word, set `reasoning_effort` to `low` or `none` where the model supports it, as the scripts in this lab do.
- **Stream from an agent.** Agent frameworks stream through the same endpoint. See
  [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md).
- **Check your proxies.** Anything between the client and the gateway, such as a reverse proxy or an API layer of your
  own, must pass `text/event-stream` responses through without buffering.

## Clean up

Delete the streaming alias. Its token limit goes with it, and the backend model and your alias from lab 02 stay.
In the portal, open `<model-name>-stream` in **Models** › **Aliases** and select **Delete**. From a shell:

```bash title="Bash"
az rest --method delete --url "$WS/aliases/$STREAM_ALIAS?$API"
```

```powershell title="PowerShell"
az rest --method delete --url "$WS/aliases/$STREAM_ALIAS`?$API"
```

Keep the gateway, model, and key. The next labs reuse them.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `IndexError: list index out of range` in Python, or `Cannot read properties of undefined` in TypeScript | The code reads `choices[0]` on the prompt filter chunk or the usage chunk, which have no choices | Skip chunks whose `choices` array is empty, as the samples do. |
| The whole reply appears at once | curl runs without `-N`, PowerShell uses `Invoke-RestMethod`, or a proxy buffers the response | Use `curl -N`, read the stream with `HttpClient` as `stream-chat.ps1` does, and turn off response buffering in your proxy. |
| No usage chunk at the end of the stream | The client didn't set `stream_options.include_usage` | Set it when your app needs the numbers. The gateway counts the tokens for its limits either way. |
| `400` with `The 'stream_options' parameter is only allowed when 'stream' is enabled.` | The request sets `stream_options` without `"stream": true` | Send both, or neither. |
| `429` JSON response instead of a stream | A token limit on the alias, the model, or the gateway is exhausted | Wait for `Retry-After` seconds. The limit is checked before the stream starts, so no partial reply is lost. |
| The SDK sample never shows a `429` | The OpenAI SDKs retry `429` responses automatically and honor `Retry-After` | That's the behavior you want in an app. To see each `429`, create the client with `max_retries=0` (Python) or `maxRetries: 0` (TypeScript). |
| Every request in the burst returns `200` | The policy isn't active yet, or the burst used another alias | Check that `STREAM_ALIAS` matches the alias with the limit, wait a minute, and run the burst again. |

## Next steps

- [Throttle tokens per caller with token limits](../06-token-limits/README.md): give every caller its own allowance.
- [Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md): cap spend in dollars.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): see streamed and throttled requests side by side.
- [September 24 release: usage for streamed Chat Completions responses](https://ai.gateway.azure.com/docs/releases/2026-09-24)
