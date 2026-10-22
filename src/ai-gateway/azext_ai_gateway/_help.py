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
      - name: List regions supported by the AI Gateway SKU.
        text: az ai-gateway create --list-regions --output table
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

helps["ai-gateway import-inventory"] = """
    type: command
    short-summary: Inventory API Management configuration for AI Gateway migration.
    long-summary: >
        Read migration-relevant configuration from an Azure API Management
        service and return a stable, versioned, redacted inventory. The command
        does not map source objects, inspect a destination, retrieve secret
        values, or change Azure resources. BasicV2, StandardV2, and PremiumV2
        use stable APIM discovery plus preview-only service MCP enrichment.
        Collection coverage and platform-health incidents distinguish empty,
        partial, failed, and inapplicable domains. Approved local APIOps
        artifacts can authoritatively recover domains declared complete in
        matching export metadata. ARM-template evidence is supplemental and
        cannot establish absence. Provenance, conflicts, and a deterministic
        source behavior ledger are included in schema 3.0. Use the ai-gateway
        plugin migration skill to turn this inventory into an
        administrator-approved migration.
    examples:
      - name: Create a structured APIM migration inventory.
        text: >-
          az ai-gateway import-inventory
          --source-apim-id /subscriptions/sub/resourceGroups/rg/providers/Microsoft.ApiManagement/service/apim
          --output json
      - name: Fill incomplete ARM discovery from local exports.
        text: >-
          az ai-gateway import-inventory
          --source-apim-id /subscriptions/sub/resourceGroups/rg/providers/Microsoft.ApiManagement/service/apim
          --apiops-artifact ./artifacts
          --arm-template-file ./template.json
          --approve-export-evidence
          --output json
      - name: Summarize inventory completeness.
        text: >-
          az ai-gateway import-inventory
          --source-apim-id /subscriptions/sub/resourceGroups/rg/providers/Microsoft.ApiManagement/service/apim
          --output table
"""

helps["ai-gateway migration-capability"] = """
    type: group
    short-summary: Inspect the machine-readable APIM migration capability contract.
"""

helps["ai-gateway migration-capability show"] = """
    type: command
    short-summary: Show the deterministic APIM migration capability contract.
    long-summary: >
        Returns stable capability IDs, supported granular destination commands,
        approval classes, idempotency strategies, verification methods, and
        limitations. The command does not read or change Azure resources.
    examples:
      - name: Save the capability contract for migration planning.
        text: >-
          az ai-gateway migration-capability show --output json
"""

helps["ai-gateway migration-plan"] = """
    type: group
    short-summary: Validate an AI-assisted APIM migration plan.
"""

helps["ai-gateway migration-plan validate"] = """
    type: command
    short-summary: Deterministically validate machine-readable migration state.
    long-summary: >
        Validates schema versions and safety-critical state shape, generation
        consistency, capability bindings, complete source behavior-ledger
        coverage, plan and approval digests, provenance conflicts, dependencies,
        command allowlisting, idempotency, verification coverage, rollback, and
        residual decisions. The command does not read or change Azure resources.
    examples:
      - name: Validate a migration checkpoint before approval or execution.
        text: >-
          az ai-gateway migration-plan validate
          --context-file .ai-gateway-migration/source-to-target/context.json
          --source-inventory-file
          .ai-gateway-migration/source-to-target/source-inventory.json
          --mapping-file .ai-gateway-migration/source-to-target/mapping.json
          --todos-file .ai-gateway-migration/source-to-target/todos.json
          --output json
"""

helps["ai-gateway model-alias"] = """
    type: group
    short-summary: Manage stable callable aliases for backend models.
"""

helps["ai-gateway model-alias create"] = """
    type: command
    short-summary: Create a model alias.
    examples:
      - name: Create a callable alias for a backend model.
        text: >-
          az ai-gateway model-alias create --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
          --alias-name production/chat --model-provider foundry
          --model-name gpt-4o
"""

helps["ai-gateway model-alias delete"] = """
    type: command
    short-summary: Delete a model alias.
    long-summary: >
        Deleting an alias immediately breaks callers using its callable name.
        The current ETag is retrieved automatically unless --if-match is set.
    examples:
      - name: Delete a model alias.
        text: >-
          az ai-gateway model-alias delete --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
"""

helps["ai-gateway model-alias list"] = """
    type: command
    short-summary: List model aliases.
    examples:
      - name: List model aliases.
        text: >-
          az ai-gateway model-alias list --resource-name my-ai-gateway
          --resource-group my-resource-group --output table
"""

helps["ai-gateway model-alias show"] = """
    type: command
    short-summary: Show a model alias.
    examples:
      - name: Show a model alias by its immutable resource ID segment.
        text: >-
          az ai-gateway model-alias show --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
"""

helps["ai-gateway model-alias test"] = """
    type: command
    short-summary: Test a model alias with a minimal inference request.
    long-summary: >
        Resolves the alias backend model, selects its chat completions,
        Responses API, or Anthropic Messages endpoint, and sends a short prompt
        using an Entra access token for ai.gateway.azure.com. If
        --api-key-name is set, the command instead uses the primary value of
        that AI Gateway API key resource. When the target model supports
        multiple endpoints, --endpoint is required. Omit --name to test every
        alias in JSON piped from az ai-gateway model-alias list.
        Set --n to a positive integer to repeat the test sequentially per alias.
        Repeated tests continue after failures, report each result, and return
        an error after all tests finish if any failed. The default is one test.
    examples:
      - name: Test a model alias with the signed-in Azure identity.
        text: >-
          az ai-gateway model-alias test --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
      - name: Test a model alias with an API key.
        text: >-
          az ai-gateway model-alias test --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
          --api-key-name production
      - name: Test a model alias with a custom prompt.
        text: >-
          az ai-gateway model-alias test --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
          --prompt "Reply with pong."
      - name: Send ten requests to test model alias policies.
        text: >-
          az ai-gateway model-alias test --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat --n 10
      - name: Test the Responses API endpoint of a multi-endpoint model.
        text: >-
          az ai-gateway model-alias test --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
          --endpoint responses
      - name: Test every listed model alias.
        text: >-
          az ai-gateway model-alias list --resource-name my-ai-gateway
          --resource-group my-resource-group --output json |
          az ai-gateway model-alias test --resource-name my-ai-gateway
          --resource-group my-resource-group --api-key-name master
"""

helps["ai-gateway model-alias update"] = """
    type: command
    short-summary: Rename or retarget a model alias.
    long-summary: >
        The command patches only supplied properties and retrieves the current
        ETag automatically unless --if-match is set. Renaming immediately stops
        the previous callable name; retargeting affects new requests immediately.
    examples:
      - name: Rename a callable alias.
        text: >-
          az ai-gateway model-alias update --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
          --alias-name production/chat-v2
      - name: Retarget an alias.
        text: >-
          az ai-gateway model-alias update --resource-name my-ai-gateway
          --resource-group my-resource-group --name production-chat
          --model-provider foundry --model-name gpt-5
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
      - name: Filter models by model provider and type.
        text: >-
          az ai-gateway model list --resource-name my-ai-gateway
          --resource-group my-resource-group --model-provider foundry
          --type Foundry
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

helps["ai-gateway model-provider"] = """
    type: group
    short-summary: Manage model providers.
"""

helps["ai-gateway model-provider create"] = """
    type: command
    short-summary: Create a Foundry or custom model provider.
    long-summary: >
        Creates the provider, then discovers and imports its models. Use
        --aliases to create provider/model callable aliases for imported models.
        Use --no-sync to create only the provider; --aliases and --no-sync cannot
        be combined. When Cognitive Services account list output is piped to this
        command, creates one Foundry provider per AIServices or OpenAI account
        using the account name, resource ID, and endpoint.
    examples:
      - name: Create providers from Cognitive Services accounts.
        text: >-
          az cognitiveservices account list
          --resource-group my-foundry-resource-group
          | az ai-gateway model-provider create
          --resource-name my-ai-gateway --resource-group my-gateway-resource-group
      - name: Create a Foundry provider using managed identity.
        text: >-
          az ai-gateway model-provider create
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name foundry --kind Foundry
          --resource-ids /subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account
          /subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account-2
          --aliases
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
        provider's OpenAI- or Anthropic-compatible /v1/models endpoint.
        Naming conflicts abort synchronization before any model changes are
        applied; use --dry-run to inspect the complete plan. Add --aliases to
        create provider/model callable aliases for newly created models. Alias
        failures are reported without rolling back successfully created models.
        Custom providers
        securely prompt for the API key when --api-key-value is omitted from an
        interactive session. Non-dry-run synchronization creates discovered
        models and deletes stale registrations, and requires --yes.
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
          --name custom --api-key-value "$PROVIDER_API_KEY" --yes
      - name: Synchronize a Foundry provider.
        text: >-
          az ai-gateway model-provider sync
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name foundry --yes
      - name: Synchronize models and create callable aliases.
        text: >-
          az ai-gateway model-provider sync
          --resource-name my-ai-gateway --resource-group my-resource-group
          --name foundry --aliases --yes
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
    short-summary: Create an MCP tool server.
    long-summary: >
        The command fails if an MCP tool server with the same name already
        exists. Use az ai-gateway mcp update to change an existing server.
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
        mode and its effect on the result. Omit --name to test every MCP tool
        server in JSON piped from az ai-gateway mcp list.
        Set --n to a positive integer to repeat the full initialize,
        notifications/initialized, and tools/list sequence per server.
        Repeated tests run sequentially, continue after failures, report each
        result, and return an error after all tests finish if any failed.
        The default is one test.
    examples:
      - name: Test an MCP tool server.
        text: >-
          az ai-gateway mcp test --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
          --api-key-name production
      - name: Test every listed MCP tool server.
        text: >-
          az ai-gateway mcp list --resource-name my-ai-gateway
          --resource-group my-resource-group --output json |
          az ai-gateway mcp test --resource-name my-ai-gateway
          --resource-group my-resource-group --api-key-name master
      - name: Repeat the MCP protocol test ten times.
        text: >-
          az ai-gateway mcp test --resource-name my-ai-gateway
          --resource-group my-resource-group --name tools
          --api-key-name production --n 10
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
    short-summary: Manage inline policies on models, aliases, and MCP tool servers.
"""

helps["ai-gateway policy create"] = """
    type: command
    short-summary: Add an inline policy to a model, alias, or MCP tool server.
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
      - name: Add a policy to a model alias.
        text: >-
          az ai-gateway policy create --resource-name my-ai-gateway
          --resource-group my-resource-group --scope-type model-alias
          --scope-name production-chat --policy @policy.json
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
    short-summary: List inline policies across models, aliases, and MCP tool servers.
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
        Returns the declarative capability registry used during AI-assisted
        migration. The output identifies supported fields,
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
