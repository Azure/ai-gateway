"""Calls a model through AI Gateway with the OpenAI Python SDK: once with the Responses API and once with
Chat Completions. The gateway authenticates the api-key header, so the SDK's own API key is a placeholder.

Usage:
  pip install -r requirements.txt
  export AI_GATEWAY_URL="https://<gateway>.azure-api.net"
  export AI_GATEWAY_MODEL="<model-alias>"
  export AI_GATEWAY_API_KEY="..."      # never commit this value
  python first-call.py
"""

import os

from openai import OpenAI

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
model = os.environ["AI_GATEWAY_MODEL"]

client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key="unused",
    default_headers={"api-key": os.environ["AI_GATEWAY_API_KEY"]},
)

response = client.responses.create(
    model=model,
    input="Write a one-sentence status update.",
)
print(f"Responses API:    {response.output_text}")

completion = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Describe an AI gateway in one sentence."}],
)
print(f"Chat Completions: {completion.choices[0].message.content}")
print(f"Tokens used:      {completion.usage.total_tokens if completion.usage else 'n/a'}")
