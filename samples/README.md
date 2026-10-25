# Samples

A curated catalog of samples that build on the [AI Gateway tier in Azure API Management](https://aka.ms/aigateway/docs), including external examples and a repository-local Terraform reference.

| Sample | Language | Description |
| ------ | -------- | ----------- |
| Foundry AI Gateway E2E | [Python](https://aka.ms/foundry-aigateway-python) / [.NET (C#)](https://aka.ms/foundry-aigateway-dotnet) | A Daily Digest Agent deployed as a Foundry Hosted Agent whose model and GitHub MCP traffic is routed through AI Gateway. |
| IaC only | [Bicep](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/ai-gateway) | Infrastructure as code for provisioning infrastructure using Bicep, scripts, or azd. Direct links to the building blocks: [AI Gateway](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/ai-gateway), [Foundry Models](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/foundry-models), and [Foundry Hosted Agent](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/main/infra/foundry-agents). |
| Terraform reference (legacy preview) | [Terraform](terraform/README.md) | AI Gateway and Foundry infrastructure with Public or Private-only networking, API-key or optional Entra access, and optional private hosted-agent infrastructure. Uses the time-limited legacy SKU; see the sample's migration notice before deployment. |
