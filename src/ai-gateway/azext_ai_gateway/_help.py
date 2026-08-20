# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from knack.help_files import helps


helps["ai-gateway"] = """
    type: group
    short-summary: Manage and use the AI Gateway SKU in Azure API Management.
"""

helps["ai-gateway api-key"] = """
    type: group
    short-summary: Manage gateway-wide data-plane API keys.
"""

helps["ai-gateway api-key create"] = """
    type: command
    short-summary: Create an API key.
    examples:
      - name: Create an API key.
        text: >-
          az ai-gateway api-key create --resource-name my-ai-gateway
          --resource-group my-resource-group --name production
          --display-name "Production applications"
"""

helps["ai-gateway api-key delete"] = """
    type: command
    short-summary: Delete an API key.
    examples:
      - name: Delete an API key.
        text: >-
          az ai-gateway api-key delete --resource-name my-ai-gateway
          --resource-group my-resource-group --name production
"""

helps["ai-gateway api-key list"] = """
    type: command
    short-summary: List API key metadata without secret values.
    examples:
      - name: List API keys.
        text: >-
          az ai-gateway api-key list --resource-name my-ai-gateway
          --resource-group my-resource-group --output table
"""

helps["ai-gateway api-key list-secrets"] = """
    type: command
    short-summary: List the primary and secondary values of an API key.
    long-summary: Treat the output as secret material. Do not persist it in logs.
    examples:
      - name: List API key values.
        text: >-
          az ai-gateway api-key list-secrets --resource-name my-ai-gateway
          --resource-group my-resource-group --name production
"""

helps["ai-gateway api-key regenerate"] = """
    type: command
    short-summary: Regenerate one value of an API key.
    examples:
      - name: Regenerate the secondary key value.
        text: >-
          az ai-gateway api-key regenerate --resource-name my-ai-gateway
          --resource-group my-resource-group --name production
          --key-type secondary
"""

helps["ai-gateway api-key show"] = """
    type: command
    short-summary: Show API key metadata without secret values.
    examples:
      - name: Show an API key.
        text: >-
          az ai-gateway api-key show --resource-name my-ai-gateway
          --resource-group my-resource-group --name production
"""

helps["ai-gateway create"] = """
    type: command
    short-summary: Create an AI Gateway.
    examples:
      - name: Create an AI Gateway with the fixed AI Gateway SKU.
        text: >-
          az ai-gateway create --name my-ai-gateway
          --resource-group my-resource-group --location eastus2
      - name: Create an AI Gateway with managed identities and tags.
        text: >-
          az ai-gateway create --name my-ai-gateway
          --resource-group my-resource-group --location eastus2
          --mi-system-assigned true
          --mi-user-assigned
          /subscriptions/s/resourceGroups/r/providers/Microsoft.ManagedIdentity/userAssignedIdentities/i
          --tags environment=production
"""

helps["ai-gateway delete"] = """
    type: command
    short-summary: Delete an AI Gateway.
    examples:
      - name: Delete an AI Gateway.
        text: >-
          az ai-gateway delete --name my-ai-gateway
          --resource-group my-resource-group
"""

helps["ai-gateway import"] = """
    type: command
    short-summary: Discover or import configuration from API Management.
    long-summary: >
        Discover models, agents, and tools in a classic Azure API Management
        service and assess whether each asset can be imported. The dry-run
        inventory includes complete source API properties, resolved backends,
        operations, policy compatibility, destination mappings, and conflicts
        without exposing credential values.
        Import execution is not available yet, so --dry-run is required.
    examples:
      - name: Inventory all assets and assess import compatibility.
        text: >-
          az ai-gateway import --name my-ai-gateway
          --resource-group my-resource-group
          --source-apim-id /subscriptions/sub/resourceGroups/rg/providers/Microsoft.ApiManagement/service/apim
          --dry-run
      - name: Inventory models and tools while planning to skip conflicts.
        text: >-
          az ai-gateway import --name my-ai-gateway
          --resource-group my-resource-group
          --source-apim-id /subscriptions/sub/resourceGroups/rg/providers/Microsoft.ApiManagement/service/apim
          --include models tools --conflict-policy skip --dry-run
          --output table
"""

helps["ai-gateway identity"] = """
    type: group
    short-summary: Manage AI Gateway managed identities.
"""

helps["ai-gateway identity assign"] = """
    type: command
    short-summary: Assign managed identities to an AI Gateway.
    examples:
      - name: Enable the system-assigned identity.
        text: >-
          az ai-gateway identity assign --resource-name my-ai-gateway
          --resource-group my-resource-group --system-assigned
      - name: Attach a user-assigned identity.
        text: >-
          az ai-gateway identity assign --resource-name my-ai-gateway
          --resource-group my-resource-group --user-assigned
          /subscriptions/s/resourceGroups/r/providers/Microsoft.ManagedIdentity/userAssignedIdentities/i
"""

helps["ai-gateway identity remove"] = """
    type: command
    short-summary: Remove managed identities from an AI Gateway.
    examples:
      - name: Disable the system-assigned identity.
        text: >-
          az ai-gateway identity remove --resource-name my-ai-gateway
          --resource-group my-resource-group --system-assigned
      - name: Detach all user-assigned identities.
        text: >-
          az ai-gateway identity remove --resource-name my-ai-gateway
          --resource-group my-resource-group --user-assigned
"""

helps["ai-gateway identity show"] = """
    type: command
    short-summary: Show managed identities assigned to an AI Gateway.
    examples:
      - name: Show managed identities.
        text: >-
          az ai-gateway identity show --resource-name my-ai-gateway
          --resource-group my-resource-group
"""

helps["ai-gateway list"] = """
    type: command
    short-summary: List AI Gateways.
    examples:
      - name: List AI Gateways in the current subscription.
        text: az ai-gateway list
      - name: List AI Gateways in a resource group.
        text: az ai-gateway list --resource-group my-resource-group
"""

helps["ai-gateway telemetry-exporter"] = """
    type: group
    short-summary: Manage AI Gateway telemetry exporters.
"""

helps["ai-gateway telemetry-exporter create"] = """
    type: command
    short-summary: Create or replace a telemetry exporter.
    long-summary: >
        For Application Insights, provide its resource ID. The command enables
        OTLP ingestion, grants the gateway identity access to the data collection
        rule, and creates the exporter. For another OpenTelemetry destination,
        provide at least one signal endpoint. Authentication is optional; use
        custom headers or managed identity when the destination requires it.
    examples:
      - name: Create an Application Insights telemetry exporter.
        text: >-
          az ai-gateway telemetry-exporter create
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name appinsights --application-insights
          /subscriptions/sub/resourceGroups/rg/providers/Microsoft.Insights/components/app
      - name: Create an exporter with payload capture and a user-assigned identity.
        text: >-
          az ai-gateway telemetry-exporter create
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name appinsights --application-insights
          /subscriptions/sub/resourceGroups/rg/providers/Microsoft.Insights/components/app
          --identity-client-id 00000000-0000-0000-0000-000000000000
          --payload-capture
      - name: Create a custom OTLP telemetry exporter with headers.
        text: >-
          az ai-gateway telemetry-exporter create
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name custom-otlp
          --metrics-endpoint https://otel.example.com/v1/metrics
          --logs-endpoint https://otel.example.com/v1/logs
          --traces-endpoint https://otel.example.com/v1/traces
          --headers '{"x-api-key":"secret"}'
"""

helps["ai-gateway telemetry-exporter delete"] = """
    type: command
    short-summary: Delete a telemetry exporter.
    examples:
      - name: Delete a telemetry exporter.
        text: >-
          az ai-gateway telemetry-exporter delete
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name appinsights
"""

helps["ai-gateway telemetry-exporter list"] = """
    type: command
    short-summary: List telemetry exporters in an AI Gateway.
    long-summary: Custom header values are redacted in the output.
    examples:
      - name: List telemetry exporters.
        text: >-
          az ai-gateway telemetry-exporter list
          --resource-name my-ai-gateway --resource-group my-resource-group
"""

helps["ai-gateway model"] = """
    type: group
    short-summary: Manage models registered in an AI Gateway.
"""

helps["ai-gateway model create"] = """
    type: command
    short-summary: Create or replace a model registration.
    examples:
      - name: Create a model backed by a Foundry deployment.
        text: >-
          az ai-gateway model create --resource-name my-ai-gateway
          --resource-group my-resource-group --provider-name foundry
          --name gpt-4o --display-name "GPT-4o"
          --deployment-model-name gpt-4o
          --deployment-resource-id
          /subscriptions/s/resourceGroups/r/providers/Microsoft.CognitiveServices/accounts/a/deployments/d
      - name: Create a custom-provider model.
        text: >-
          az ai-gateway model create --resource-name my-ai-gateway
          --resource-group my-resource-group --provider-name custom
          --name llama --api-format OpenAIChatCompletions
          --supported-endpoints /v1/chat/completions
"""

helps["ai-gateway model delete"] = """
    type: command
    short-summary: Delete a model registration.
    examples:
      - name: Delete a model.
        text: >-
          az ai-gateway model delete --resource-name my-ai-gateway
          --resource-group my-resource-group --provider-name foundry
          --name gpt-4o
"""

helps["ai-gateway model list"] = """
    type: command
    short-summary: List model registrations.
    examples:
      - name: List models across every provider.
        text: >-
          az ai-gateway model list --resource-name my-ai-gateway
          --resource-group my-resource-group --output table
      - name: List models belonging to one provider.
        text: >-
          az ai-gateway model list --resource-name my-ai-gateway
          --resource-group my-resource-group --provider-name foundry
"""

helps["ai-gateway model show"] = """
    type: command
    short-summary: Show a model registration.
    examples:
      - name: Show a model.
        text: >-
          az ai-gateway model show --resource-name my-ai-gateway
          --resource-group my-resource-group --provider-name foundry
          --name gpt-4o
"""

helps["ai-gateway model update"] = """
    type: command
    short-summary: Update a model registration.
    examples:
      - name: Update model metadata and supported endpoints.
        text: >-
          az ai-gateway model update --resource-name my-ai-gateway
          --resource-group my-resource-group --provider-name custom
          --name llama --description "Production model"
          --supported-endpoints /v1/chat/completions /v1/responses
      - name: Replace inline policies from a JSON file.
        text: >-
          az ai-gateway model update --resource-name my-ai-gateway
          --resource-group my-resource-group --provider-name foundry
          --name gpt-4o --policies @policies.json
"""

helps["ai-gateway model-provider"] = """
    type: group
    short-summary: Manage model providers.
"""

helps["ai-gateway model-provider create"] = """
    type: command
    short-summary: Create a Foundry or custom model provider.
    long-summary: >
        Creates the provider, then discovers and imports its models. Use
        --no-sync to create only the provider.
    examples:
      - name: Create a Foundry provider using managed identity.
        text: >-
          az ai-gateway model-provider create
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name foundry --kind Foundry
          --resource-ids /subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account
          /subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account-2
          --managed-identity-resource https://cognitiveservices.azure.com
      - name: Create a custom provider using an API key.
        text: >-
          az ai-gateway model-provider create
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name custom --kind Custom
          --endpoint https://models.example.com
          --api-key-header-name Authorization
          --api-key-value "$PROVIDER_API_KEY"
      - name: Create a provider without importing models.
        text: >-
          az ai-gateway model-provider create
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name custom --kind Custom
          --endpoint https://models.example.com
          --api-key-header-name Authorization
          --api-key-value "$PROVIDER_API_KEY" --no-sync
"""

helps["ai-gateway model-provider delete"] = """
    type: command
    short-summary: Delete a model provider.
    examples:
      - name: Delete a model provider.
        text: >-
          az ai-gateway model-provider delete
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name custom
"""

helps["ai-gateway model-provider list"] = """
    type: command
    short-summary: List model providers.
    examples:
      - name: List model providers.
        text: >-
          az ai-gateway model-provider list
          --resource-name my-ai-gateway --resource-group my-resource-group
          --output table
"""

helps["ai-gateway model-provider show"] = """
    type: command
    short-summary: Show a model provider.
    examples:
      - name: Show a model provider.
        text: >-
          az ai-gateway model-provider show
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name foundry
"""

helps["ai-gateway model-provider sync"] = """
    type: command
    short-summary: Synchronize models from a model provider.
    long-summary: >
        Creates registrations from Foundry deployments or from a custom
        provider's OpenAI- or Anthropic-compatible /v1/models endpoint and
        reports naming conflicts. Custom providers securely prompt for the API
        key when --api-key-value is omitted from an interactive session. Stale
        registrations are deleted only with --delete-missing.
    examples:
      - name: Preview synchronization changes.
        text: >-
          az ai-gateway model-provider sync
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name foundry --dry-run --output table
      - name: Synchronize a custom provider.
        text: >-
          az ai-gateway model-provider sync
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name custom --api-key-value "$PROVIDER_API_KEY"
      - name: Synchronize and delete stale registrations.
        text: >-
          az ai-gateway model-provider sync
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name foundry --delete-missing --yes
"""

helps["ai-gateway model-provider update"] = """
    type: command
    short-summary: Update a model provider.
    long-summary: >
        Provider kind is immutable. Omitted API key values remain unchanged.
    examples:
      - name: Update a provider display name.
        text: >-
          az ai-gateway model-provider update
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name custom --display-name "Custom Models"
      - name: Rotate a custom provider API key.
        text: >-
          az ai-gateway model-provider update
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name custom --api-key-value "$PROVIDER_API_KEY"
"""

helps["ai-gateway mcp"] = """
    type: group
    short-summary: Manage MCP tool servers registered in an AI Gateway.
"""

helps["ai-gateway mcp authorize"] = """
    type: command
    short-summary: Get OAuth login links for an MCP tool server endpoint.
    examples:
      - name: Start OAuth authorization for an endpoint.
        text: >-
          az ai-gateway mcp authorize --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
          --endpoint-id endpoint-id
"""

helps["ai-gateway mcp create"] = """
    type: command
    short-summary: Create or replace an MCP tool server.
    examples:
      - name: Create an MCP tool server from an endpoint definition file.
        text: >-
          az ai-gateway mcp create --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
          --display-name "Team tools" --failure-mode failClosed
          --endpoints @endpoints.json
"""

helps["ai-gateway mcp delete"] = """
    type: command
    short-summary: Delete an MCP tool server.
    examples:
      - name: Delete an MCP tool server.
        text: >-
          az ai-gateway mcp delete --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
"""

helps["ai-gateway mcp list"] = """
    type: command
    short-summary: List MCP tool servers and their runtime endpoints.
    examples:
      - name: List MCP tool servers.
        text: >-
          az ai-gateway mcp list --resource-name my-ai-gateway
          --resource-group my-resource-group --output table
"""

helps["ai-gateway mcp show"] = """
    type: command
    short-summary: Show an MCP tool server with secret fields redacted.
    examples:
      - name: Show an MCP tool server.
        text: >-
          az ai-gateway mcp show --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
"""

helps["ai-gateway mcp test"] = """
    type: command
    short-summary: Test an MCP tool server by performing protocol initialization.
    long-summary: >
        Builds the MCP endpoint from the AI Gateway runtime URL, workspace, and
        tool-server name, performs initialization, and lists the tools exposed
        by the server. Failures show attempted protocol stages in execution
        order, followed by a structured federation diagnosis and the full failed
        HTTP response. Before testing, the command states the configured failure
        mode and its effect on the result.
    examples:
      - name: Test an MCP tool server.
        text: >-
          az ai-gateway mcp test --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
          --api-key-name production
"""

helps["ai-gateway mcp update"] = """
    type: command
    short-summary: Update an MCP tool server.
    long-summary: >
        Endpoint updates preserve stored secrets by reading them internally
        and use ETags to reject concurrent writes. Secrets are never emitted.
    examples:
      - name: Update metadata without replacing endpoints.
        text: >-
          az ai-gateway mcp update --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
          --description "Production tool federation"
      - name: Replace endpoints from a definition file.
        text: >-
          az ai-gateway mcp update --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
          --endpoints @endpoints.json
"""

helps["ai-gateway policy"] = """
    type: group
    short-summary: Manage inline policies on models and MCP tool servers.
"""

helps["ai-gateway policy create"] = """
    type: command
    short-summary: Add an inline policy to a model or MCP tool server.
    examples:
      - name: Add a token-limit policy to a model.
        text: >-
          az ai-gateway policy create --resource-name my-ai-gateway
          --resource-group my-resource-group --scope-type model
          --scope-name gpt-4o --provider-name foundry
          --policy @policy.json
      - name: Add a content-safety policy to an MCP tool server.
        text: >-
          az ai-gateway policy create --resource-name my-ai-gateway
          --resource-group my-resource-group --scope-type mcp
          --scope-name tools --policy @policy.json
"""

helps["ai-gateway policy delete"] = """
    type: command
    short-summary: Delete an inline policy.
    examples:
      - name: Delete a policy returned by policy list.
        text: >-
          az ai-gateway policy delete --resource-name my-ai-gateway
          --resource-group my-resource-group --policy-id policy-id
"""

helps["ai-gateway policy list"] = """
    type: command
    short-summary: List inline policies across models and MCP tool servers.
    examples:
      - name: List every policy.
        text: >-
          az ai-gateway policy list --resource-name my-ai-gateway
          --resource-group my-resource-group --output table
      - name: List policies on one model.
        text: >-
          az ai-gateway policy list --resource-name my-ai-gateway
          --resource-group my-resource-group --scope-type model
          --scope-name gpt-4o --provider-name foundry
"""

helps["ai-gateway policy show"] = """
    type: command
    short-summary: Show an inline policy.
    examples:
      - name: Show a policy returned by policy list.
        text: >-
          az ai-gateway policy show --resource-name my-ai-gateway
          --resource-group my-resource-group --policy-id policy-id
"""

helps["ai-gateway policy update"] = """
    type: command
    short-summary: Replace an inline policy.
    long-summary: The supplied JSON object replaces the complete policy.
    examples:
      - name: Replace a policy from a JSON file.
        text: >-
          az ai-gateway policy update --resource-name my-ai-gateway
          --resource-group my-resource-group --policy-id policy-id
          --policy @policy.json
"""

helps["ai-gateway policy import-support"] = """
    type: group
    short-summary: Inspect APIM-to-AI-Gateway policy translation capabilities.
"""

helps["ai-gateway policy import-support list"] = """
    type: command
    short-summary: List known APIM policy translation capabilities.
    long-summary: >
        Returns the same declarative capability registry used by
        az ai-gateway import. The output identifies supported fields,
        unsupported fields, destination policy types, valid sections, and
        scope behavior.
    examples:
      - name: List all known policy capabilities.
        text: az ai-gateway policy import-support list --output table
      - name: List policies that currently have no destination mapping.
        text: >-
          az ai-gateway policy import-support list
          --support-level unsupported --output table
"""

helps["ai-gateway policy import-support show"] = """
    type: command
    short-summary: Show one APIM policy translation capability.
    examples:
      - name: Inspect token-limit translation support.
        text: >-
          az ai-gateway policy import-support show
          --name llm-token-limit --output json
"""

helps["ai-gateway show"] = """
    type: command
    short-summary: Show an AI Gateway.
    examples:
      - name: Show an AI Gateway.
        text: >-
          az ai-gateway show --name my-ai-gateway
          --resource-group my-resource-group
"""

helps["ai-gateway update"] = """
    type: command
    short-summary: Update an AI Gateway.
    examples:
      - name: Update gateway tags and public network access.
        text: >-
          az ai-gateway update --name my-ai-gateway
          --resource-group my-resource-group
          --tags environment=production
          --public-network-access Disabled
      - name: Configure outbound virtual network integration.
        text: >-
          az ai-gateway update --name my-ai-gateway
          --resource-group my-resource-group
          --virtual-network-type External
          --subnet-resource-id /subscriptions/s/resourceGroups/r/providers/Microsoft.Network/virtualNetworks/v/subnets/s
      - name: Disable outbound virtual network integration and clear its subnet.
        text: >-
          az ai-gateway update --name my-ai-gateway
          --resource-group my-resource-group
          --virtual-network-type None
"""

helps["ai-gateway private-endpoint"] = """
    type: group
    short-summary: Manage service-side private endpoint connections.
"""

helps["ai-gateway private-endpoint list"] = """
    type: command
    short-summary: List private endpoint connections for an AI Gateway.
    examples:
      - name: List private endpoint connections.
        text: >-
          az ai-gateway private-endpoint list
          --resource-name my-ai-gateway
          --resource-group my-resource-group --output table
"""

helps["ai-gateway private-endpoint show"] = """
    type: command
    short-summary: Show a private endpoint connection.
"""

helps["ai-gateway private-endpoint approve"] = """
    type: command
    short-summary: Approve a private endpoint connection.
    examples:
      - name: Approve a pending connection.
        text: >-
          az ai-gateway private-endpoint approve
          --name connection-name --description "Approved"
          --resource-name my-ai-gateway
          --resource-group my-resource-group
"""

helps["ai-gateway private-endpoint reject"] = """
    type: command
    short-summary: Reject a private endpoint connection.
    examples:
      - name: Reject a pending connection.
        text: >-
          az ai-gateway private-endpoint reject
          --name connection-name --description "Not approved"
          --resource-name my-ai-gateway
          --resource-group my-resource-group
"""

helps["ai-gateway private-endpoint delete"] = """
    type: command
    short-summary: Delete a service-side private endpoint connection.
    long-summary: >
        This does not delete the backing Microsoft.Network private endpoint.
"""

helps["ai-gateway version"] = """
    type: command
    short-summary: Show the installed AI Gateway extension version.
    examples:
      - name: Show the extension version.
        text: az ai-gateway version
"""
