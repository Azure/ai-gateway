# Samples

A curated catalog of samples that build on the [AI Gateway tier in Azure API Management](https://aka.ms/aigateway/docs). Samples are linked from their own repositories, with a local Terraform infrastructure sample below.

| Sample | Language | Description |
| ------ | -------- | ----------- |
| Foundry AI Gateway E2E | [Python](https://aka.ms/foundry-aigateway-python) / [.NET (C#)](https://aka.ms/foundry-aigateway-dotnet) | A Daily Digest Agent deployed as a Foundry Hosted Agent whose model and GitHub MCP traffic is routed through AI Gateway. |
| IaC only | [Bicep](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/ai-gateway) / [Terraform](terraform/README.md) | Infrastructure as code for AI Gateway, Foundry Models, and Foundry Hosted Agent infrastructure. Bicep building blocks: [AI Gateway](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/ai-gateway), [Foundry Models](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/foundry-models), and [Foundry Hosted Agent](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/foundry-agents). The Terraform sample provisions all three building blocks together and includes an optional [private-connectivity PoC profile](terraform/README.md#private-connectivity-poc-profile) (gateway public access remains enabled). |
