mock_provider "azapi" {}

override_resource {
  target          = azapi_resource.insights["gateway"]
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway/providers/Microsoft.Insights/components/gateway"
    output = {
      properties = {
        DataCollectionRuleResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/managed-monitoring/providers/Microsoft.Insights/dataCollectionRules/gateway"
        OTLPMetricsEndpoint          = "https://test.metrics.ingest.monitor.azure.com/dataCollectionRules/dcr-test/streams/Microsoft-OTLP-Metrics/otlp/v1/metrics"
        OTLPLogsEndpoint             = "https://test.ingest.monitor.azure.com/dataCollectionRules/dcr-test/streams/Microsoft-OTLP-Logs/otlp/v1/logs"
        OTLPTracesEndpoint           = "https://test.ingest.monitor.azure.com/dataCollectionRules/dcr-test/streams/Microsoft-OTLP-Traces/otlp/v1/traces"
      }
    }
  }
}

override_resource {
  target          = azapi_resource.resource_group["gateway"]
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway"
  }
}

variables {
  subscription_id               = "00000000-0000-0000-0000-000000000001"
  location                      = "eastus2"
  gateway_location              = "swedencentral"
  publisher_email               = "test@example.com"
  enable_private_networking     = false
  enable_private_test_client    = false
  gateway_public_network_access = "Enabled"
  models_public_network_access  = "Enabled"
  model_deployments = {
    test-model = {
      model_name    = "test-model-name"
      model_version = "test-version"
      capacity      = 7
      token_limit   = 2300
      endpoints     = ["/openai/v1/responses"]
    }
  }
}

run "models_and_access_without_developer" {
  command = plan

  assert {
    condition = (
      length(azapi_resource.resource_group) == 1 &&
      azapi_resource.resource_group["gateway"].name == "rg-${var.environment_name}-${local.resource_token}-gateway" &&
      output.resource_group_name == azapi_resource.resource_group["gateway"].name &&
      jsonencode(keys(output.resource_groups)) == jsonencode(["agents", "gateway", "models"]) &&
      alltrue([for name in values(output.resource_groups) : name == output.resource_group_name]) &&
      alltrue([for parent in concat([
        azapi_resource.gateway.parent_id,
        azapi_resource.connector_gateway.parent_id,
        azapi_resource.models.parent_id,
        azapi_resource.agents.parent_id,
        azapi_resource.storage.parent_id,
        azapi_resource.registry.parent_id
        ], [for workspace in azapi_resource.logs : workspace.parent_id],
        [for insights in azapi_resource.insights : insights.parent_id]
      ) : parent == azapi_resource.resource_group["gateway"].id]) &&
      length(azapi_resource.logs) == 2 &&
      length(azapi_resource.insights) == 2 &&
      azapi_resource.gateway.body.sku.name == "AIGateway"
    )
    error_message = "All building blocks must share the retained gateway group without changing its name/address, AIGateway SKU, monitoring stacks or compatibility output keys."
  }

  override_resource {
    target          = azapi_resource.catalog_model["test-model"]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.ApiManagement/service/test/workspaces/default/modelProviders/foundry/models/test-model"
    }
  }

  assert {
    condition = (
      azapi_resource.model_deployment["test-model"].body.properties.model.name == "test-model-name" &&
      azapi_resource.model_deployment["test-model"].body.properties.model.version == "test-version" &&
      azapi_resource.model_deployment["test-model"].body.sku.capacity == 7 &&
      azapi_resource.catalog_model["test-model"].body.properties.deployment.modelName == "test-model" &&
      azapi_resource.catalog_model["test-model"].body.properties.policies[0].count == 2300 &&
      jsonencode(azapi_resource.catalog_model["test-model"].body.properties.policies[0].counterKey) == jsonencode(["identity"]) &&
      azapi_resource.catalog_model["test-model"].body.properties.supportedEndpoints[0] == "/openai/v1/responses"
    )
    error_message = "Deployment inputs must propagate to both Foundry and the gateway catalog without conflating quota and token limits."
  }

  assert {
    condition = (
      output.model_api_configuration["test-model"].api_format == "OpenAIChatCompletions" &&
      jsonencode(output.model_api_configuration["test-model"].endpoints) == jsonencode(["/openai/v1/responses"])
    )
    error_message = "Probe metadata must preserve the configured API, including Responses-only models that the chat probes cannot test."
  }

  assert {
    condition = (
      length(azapi_resource.model_alias) == length(var.model_deployments) &&
      azapi_resource.model_alias["test-model"].body.properties.aliasName == "test-model" &&
      azapi_resource.model_alias["test-model"].body.properties.backendModels[0].resourceId == azapi_resource.catalog_model["test-model"].id
    )
    error_message = "Every runtime model alias must route the configured deployment name to its provider catalog entry."
  }

  assert {
    condition = (
      azapi_resource.gateway.location == "swedencentral" &&
      azapi_resource.models.location == "eastus2" &&
      azapi_resource.agents.location == "eastus2"
    )
    error_message = "The gateway region must be independently configurable from the Foundry region."
  }

  assert {
    condition = (
      length(azapi_resource.role_assignment) == 7 &&
      length(azapi_resource.private_endpoint) == 0 &&
      length(azapi_resource.private_test_vm) == 0 &&
      length(azapi_resource.private_agents) == 0 &&
      length(azapi_resource.private_agent_endpoint) == 0 &&
      length(azapi_resource.private_agent_role_assignment) == 0 &&
      length(azapi_resource.private_agent_key_role) == 0 &&
      output.private_hosted_agent == null &&
      alltrue([for key in keys(azapi_resource.role_assignment) : !startswith(key, "developer-")])
    )
    error_message = "No developer access may be created unless a principal is supplied."
  }

  assert {
    condition = (
      azapi_resource.models.body.properties.disableLocalAuth &&
      azapi_resource.agents.body.properties.disableLocalAuth &&
      !azapi_resource.storage.body.properties.allowSharedKeyAccess &&
      !azapi_resource.storage.body.properties.allowBlobPublicAccess &&
      !azapi_resource.registry.body.properties.adminUserEnabled &&
      !azapi_resource.telemetry_exporter.body.properties.payloadCapture
    )
    error_message = "The sample must preserve identity-based backend access and avoid storage keys, public blobs, registry admin credentials, and payload capture."
  }
}

run "explicit_developer_service_principal" {
  command = plan
  variables {
    developer_principal_id        = "00000000-0000-0000-0000-000000000002"
    developer_principal_type      = "ServicePrincipal"
    storage_public_network_access = "Disabled"
  }

  assert {
    condition = (
      length(azapi_resource.role_assignment) == 14 &&
      alltrue([
        for key, binding in azapi_resource.role_assignment :
        binding.body.properties.principalId == var.developer_principal_id &&
        binding.body.properties.principalType == "ServicePrincipal"
        if startswith(key, "developer-")
      ])
    )
    error_message = "Explicit developer access must use the supplied principal ID/type for both accounts and storage."
  }

  assert {
    condition     = azapi_resource.storage.body.properties.publicNetworkAccess == var.storage_public_network_access
    error_message = "Storage networking must honor the configured policy-compatible access mode."
  }
}

run "reject_invalid_capacity" {
  command = plan
  variables {
    model_deployments = {
      invalid = {
        model_name    = "test-model"
        model_version = "test-version"
        capacity      = 0
        token_limit   = 1000
      }
    }
  }
  expect_failures = [var.model_deployments]
}

run "backend_rebuild_retains_gateway" {
  command = plan
  variables {
    backend_revision              = "single-group-20261023"
    retain_legacy_resource_groups = true
  }

  assert {
    condition = (
      local.backend_token != local.resource_token &&
      local.names.gateway == "aigw-${local.resource_token}" &&
      azapi_resource.resource_group["gateway"].name == "rg-${var.environment_name}-${local.resource_token}-gateway" &&
      length(azapi_resource.resource_group) == 3 &&
      local.names.models == "aimodels-${local.backend_token}" &&
      local.names.agents == "aiagents-${local.backend_token}" &&
      local.names.project == "proj-${local.backend_token}" &&
      local.names.storage == "st${local.backend_token}" &&
      local.names.registry == "acr${local.backend_token}" &&
      alltrue([for parent in [
        azapi_resource.models.parent_id,
        azapi_resource.agents.parent_id,
        azapi_resource.storage.parent_id,
        azapi_resource.registry.parent_id,
        azapi_resource.logs["agents"].parent_id,
        azapi_resource.insights["agents"].parent_id
      ] : parent == azapi_resource.resource_group["gateway"].id]) &&
      alltrue([for name in values(output.resource_groups) : name == output.resource_group_name])
    )
    error_message = "A backend revision must change only backend names, keep gateway identity and place new resources in the shared group while old groups are retained for staged cleanup."
  }
}

run "reject_invalid_backend_revision" {
  command = plan
  variables {
    backend_revision = "Invalid_Revision"
  }
  expect_failures = [var.backend_revision]
}

run "reject_empty_models" {
  command = plan
  variables {
    model_deployments = {}
  }
  expect_failures = [var.model_deployments]
}

run "private_gateway_and_model_paths" {
  command = plan
  variables {
    enable_private_networking          = true
    gateway_public_network_access      = "Disabled"
    models_public_network_access       = "Disabled"
    enable_private_test_client         = true
    private_test_client_ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleOnlyNotForDeployment"
  }
  override_resource {
    target          = azapi_resource.private_subnet["gateway"]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.Network/virtualNetworks/test/subnets/gateway"
    }
  }

  assert {
    condition = (
      length(azapi_resource.resource_group) == 1 &&
      alltrue([for parent in concat([
        azapi_resource.private_vnet[0].parent_id,
        azapi_resource.private_test_nic[0].parent_id,
        azapi_resource.private_test_vm[0].parent_id
        ], [for endpoint in azapi_resource.private_endpoint : endpoint.parent_id],
        [for zone in azapi_resource.private_dns_zone : zone.parent_id],
        [for nsg in azapi_resource.private_nsg : nsg.parent_id]
      ) : parent == azapi_resource.resource_group["gateway"].id]) &&
      jsonencode(azapi_resource.private_test_key_role[0].body.properties.assignableScopes) == jsonencode([azapi_resource.resource_group["gateway"].id]) &&
      alltrue([for endpoint in azapi_resource.private_endpoint : jsonencode(endpoint.replace_triggers_refs) == jsonencode(["properties.privateLinkServiceConnections"])])
    )
    error_message = "Private networking, DNS and the test client must remain in the shared gateway group, replace endpoints when service targets change and preserve the custom role's assignable scope."
  }

  assert {
    condition = (
      azapi_resource.gateway.body.properties.virtualNetworkType == "External" &&
      azapi_resource.gateway.body.properties.virtualNetworkConfiguration.subnetResourceId == azapi_resource.private_subnet["gateway"].id &&
      azapi_resource.gateway.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.models.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.models.body.properties.networkAcls.defaultAction == "Deny"
    )
    error_message = "Private traffic needs External plus a subnet; None plus a subnet silently loses the integration. Public switches must propagate."
  }

  assert {
    condition = (
      azapi_resource.private_subnet["gateway"].body.properties.delegations[0].properties.serviceName == "Microsoft.Web/serverFarms" &&
      azapi_resource.private_subnet["gateway"].body.properties.addressPrefix != azapi_resource.private_subnet["endpoints"].body.properties.addressPrefix &&
      azapi_resource.private_subnet["endpoints"].body.properties.privateEndpointNetworkPolicies == "Disabled" &&
      azapi_resource.private_endpoint["gateway"].body.properties.privateLinkServiceConnections[0].properties.groupIds[0] == "Gateway" &&
      azapi_resource.private_endpoint["models"].body.properties.privateLinkServiceConnections[0].properties.groupIds[0] == "account" &&
      length(azapi_resource.private_dns_zone) == 4 &&
      length(azapi_resource.private_dns_zone_group["models"].body.properties.privateDnsZoneConfigs) == 3 &&
      alltrue([for link in azapi_resource.private_dns_link : !link.body.properties.registrationEnabled])
    )
    error_message = "Separate subnets, the exact PE group IDs, all model DNS zones, and non-registering VNet links are required."
  }

  assert {
    condition = (
      !can(azapi_resource.private_test_nic[0].body.properties.ipConfigurations[0].properties.publicIPAddress) &&
      azapi_resource.private_test_vm[0].body.properties.osProfile.linuxConfiguration.disablePasswordAuthentication &&
      azapi_resource.private_nsg["client"].body.properties.securityRules[0].properties.access == "Deny" &&
      jsonencode(azapi_resource.private_test_key_role[0].body.properties.permissions[0].actions) == jsonencode(["Microsoft.ApiManagement/service/apiKeys/listSecrets/action"]) &&
      azapi_resource.agents.body.properties.publicNetworkAccess == "Enabled" &&
      azapi_resource.registry.body.properties.publicNetworkAccess == "Enabled"
    )
    error_message = "The private probe must have no public NIC/password/inbound access, only key retrieval permission, and must not change agent networking."
  }
}

run "private_connectivity_poc_profile" {
  command = plan
  variables {
    enable_private_networking                = jsondecode(file("profiles/private-connectivity.tfvars.json")).enable_private_networking
    gateway_private_endpoint_manual_approval = jsondecode(file("profiles/private-connectivity.tfvars.json")).gateway_private_endpoint_manual_approval
    gateway_public_network_access            = jsondecode(file("profiles/private-connectivity.tfvars.json")).gateway_public_network_access
    models_public_network_access             = jsondecode(file("profiles/private-connectivity.tfvars.json")).models_public_network_access
  }

  override_resource {
    target          = azapi_resource.gateway
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.ApiManagement/service/gateway"
      identity = {
        type         = "SystemAssigned"
        principal_id = "00000000-0000-0000-0000-000000000003"
        tenant_id    = "00000000-0000-0000-0000-000000000004"
      }
      output = {
        properties = { gatewayUrl = "https://test-gateway.azure-api.net" }
      }
    }
  }

  override_resource {
    target          = azapi_resource.models
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/models"
      output = {
        properties = { endpoint = "https://test-models.cognitiveservices.azure.com/" }
      }
    }
  }

  override_resource {
    target          = azapi_resource.private_subnet["gateway"]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.Network/virtualNetworks/test/subnets/gateway"
    }
  }

  assert {
    condition = (
      azapi_resource.gateway.body.sku.name == "AIGateway" &&
      azapi_resource.gateway.body.properties.publicNetworkAccess == "Enabled" &&
      azapi_resource.gateway.body.properties.virtualNetworkType == "External" &&
      azapi_resource.gateway.body.properties.virtualNetworkConfiguration.subnetResourceId == azapi_resource.private_subnet["gateway"].id &&
      azapi_resource.models.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.models.body.properties.networkAcls.defaultAction == "Deny"
    )
    error_message = "The hybrid profile must retain AIGateway, public gateway ingress, outbound integration and private models."
  }

  assert {
    condition = (
      length(azapi_resource.private_endpoint) == 2 &&
      length(azapi_resource.private_dns_zone) == 4 &&
      azapi_resource.private_endpoint["gateway"].body.properties.manualPrivateLinkServiceConnections[0].properties.privateLinkServiceId == azapi_resource.gateway.id &&
      !can(azapi_resource.private_endpoint["gateway"].body.properties.privateLinkServiceConnections) &&
      endswith(azapi_resource.private_endpoint["gateway"].name, "-gateway-manual-pe") &&
      azapi_resource.private_endpoint["gateway"].body.properties.manualPrivateLinkServiceConnections[0].name == "gateway-manual" &&
      jsonencode(azapi_resource.private_endpoint["gateway"].replace_triggers_refs) == jsonencode(["properties.manualPrivateLinkServiceConnections"]) &&
      length(azapi_resource_action.gateway_private_endpoint_approval) == 1 &&
      data.azapi_resource.gateway_private_endpoint_connection[0].parent_id == azapi_resource.gateway.id &&
      data.azapi_resource.gateway_private_endpoint_connection[0].name == "gateway-manual" &&
      azapi_resource_action.gateway_private_endpoint_approval[0].when == "apply" &&
      azapi_resource_action.gateway_private_endpoint_approval[0].resource_id == "${azapi_resource.gateway.id}/privateEndpointConnections/gateway-manual" &&
      azapi_resource.private_endpoint["models"].body.properties.privateLinkServiceConnections[0].properties.privateLinkServiceId == azapi_resource.models.id &&
      length(azapi_resource.private_test_vm) == 0 &&
      azapi_resource.agents.body.properties.publicNetworkAccess == "Enabled" &&
      azapi_resource.registry.body.properties.publicNetworkAccess == "Enabled"
    )
    error_message = "The profile must wire both private endpoints/DNS without forcing a billable VM or changing hosted-agent networking."
  }

  assert {
    condition = (
      azapi_resource.models.body.properties.disableLocalAuth &&
      azapi_resource.foundry_provider.body.properties.foundry.authentication.kind == "ManagedIdentity" &&
      azapi_resource.foundry_provider.body.properties.foundry.authentication.managedIdentity.resource == "https://cognitiveservices.azure.com/" &&
      azapi_resource.role_assignment["gateway-foundry-user"].parent_id == azapi_resource.models.id &&
      azapi_resource.role_assignment["gateway-foundry-user"].body.properties.principalId == azapi_resource.gateway.identity[0].principal_id &&
      endswith(azapi_resource.role_assignment["gateway-foundry-user"].body.properties.roleDefinitionId, "/53ca6127-db72-4b80-b1b0-d745d6d5456d")
    )
    error_message = "The private backend must keep local auth disabled and use the gateway identity with Foundry User at model-account scope."
  }

  assert {
    condition = (
      azapi_resource.runtime_api_key.parent_id == azapi_resource.gateway.id &&
      azapi_resource.telemetry_exporter.parent_id == "${azapi_resource.gateway.id}/workspaces/default" &&
      azapi_resource.telemetry_exporter.body.properties.kind == "OpenTelemetry" &&
      !azapi_resource.telemetry_exporter.body.properties.payloadCapture &&
      azapi_resource.insights["gateway"].body.properties.AzureMonitorWorkspaceIngestionMode == "Enabled" &&
      !can(azapi_resource.insights["agents"].body.properties.AzureMonitorWorkspaceIngestionMode) &&
      !can(azapi_resource.telemetry_exporter.body.properties.applicationInsights.connectionString) &&
      azapi_resource.telemetry_exporter.body.properties.applicationInsights.resourceId == azapi_resource.insights["gateway"].id &&
      azapi_resource.telemetry_exporter.body.properties.openTelemetry.metricsEndpoint == azapi_resource.insights["gateway"].output.properties.OTLPMetricsEndpoint &&
      azapi_resource.telemetry_exporter.body.properties.openTelemetry.logsEndpoint == azapi_resource.insights["gateway"].output.properties.OTLPLogsEndpoint &&
      azapi_resource.telemetry_exporter.body.properties.openTelemetry.tracesEndpoint == azapi_resource.insights["gateway"].output.properties.OTLPTracesEndpoint &&
      azapi_resource.telemetry_exporter.body.properties.openTelemetry.credentials.managedIdentity.resource == "https://monitor.azure.com" &&
      azapi_resource.role_assignment["gateway-monitoring-publisher"].parent_id == azapi_resource.insights["gateway"].output.properties.DataCollectionRuleResourceId &&
      azapi_resource.role_assignment["gateway-monitoring-publisher"].body.properties.principalId == azapi_resource.gateway.identity[0].principal_id &&
      endswith(azapi_resource.role_assignment["gateway-monitoring-publisher"].body.properties.roleDefinitionId, "/3913510d-42f4-4e42-8a64-420c390055eb")
    )
    error_message = "The profile must retain gateway API-key provisioning and workspace telemetry without payload capture."
  }
}

run "private_only_profile" {
  command = plan
  variables {
    enable_private_networking                = jsondecode(file("profiles/private-only.tfvars.json")).enable_private_networking
    gateway_private_endpoint_manual_approval = jsondecode(file("profiles/private-only.tfvars.json")).gateway_private_endpoint_manual_approval
    gateway_public_network_access            = jsondecode(file("profiles/private-only.tfvars.json")).gateway_public_network_access
    models_public_network_access             = jsondecode(file("profiles/private-only.tfvars.json")).models_public_network_access
  }

  assert {
    condition = (
      azapi_resource.gateway.body.sku.name == "AIGateway" &&
      azapi_resource.gateway.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.gateway.body.properties.virtualNetworkType == "External" &&
      azapi_resource.models.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.models.body.properties.networkAcls.defaultAction == "Deny" &&
      length(azapi_resource.private_endpoint) == 2 &&
      length(azapi_resource.private_dns_zone) == 4 &&
      length(azapi_resource.private_endpoint["gateway"].body.properties.manualPrivateLinkServiceConnections) == 1 &&
      length(azapi_resource_action.gateway_private_endpoint_approval) == 1 &&
      length(azapi_resource.private_test_vm) == 0 &&
      azapi_resource.agents.body.properties.publicNetworkAccess == "Enabled" &&
      azapi_resource.registry.body.properties.publicNetworkAccess == "Enabled"
    )
    error_message = "The private-only end-state profile must disable gateway/model public access, retain private networking, and not imply private agent execution or force a VM."
  }
}

run "reject_private_client_without_network" {
  command = plan
  variables {
    enable_private_test_client         = true
    private_test_client_ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleOnlyNotForDeployment"
  }

  expect_failures = [var.enable_private_test_client]
}

run "reject_manual_endpoint_without_network" {
  command = plan
  variables {
    gateway_private_endpoint_manual_approval = true
  }
  expect_failures = [var.gateway_private_endpoint_manual_approval]
}

run "reject_incomplete_otlp_destination" {
  command = plan
  override_resource {
    target          = azapi_resource.insights["gateway"]
    override_during = plan
    values = {
      output = {
        properties = {
          DataCollectionRuleResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/managed-monitoring/providers/Microsoft.Insights/dataCollectionRules/gateway"
        }
      }
    }
  }
  expect_failures = [azapi_resource.telemetry_exporter]
}

run "reject_subscription_scoped_monitoring_publisher" {
  command = plan
  override_resource {
    target          = azapi_resource.insights["gateway"]
    override_during = plan
    values = {
      output = {
        properties = {
          DataCollectionRuleResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001"
          OTLPMetricsEndpoint          = "https://test.metrics.ingest.monitor.azure.com/dataCollectionRules/dcr-test/metrics"
          OTLPLogsEndpoint             = "https://test.ingest.monitor.azure.com/dataCollectionRules/dcr-test/logs"
          OTLPTracesEndpoint           = "https://test.ingest.monitor.azure.com/dataCollectionRules/dcr-test/traces"
        }
      }
    }
  }
  expect_failures = [azapi_resource.role_assignment["gateway-monitoring-publisher"]]
}

run "reject_public_disable_without_network" {
  command = plan
  variables {
    gateway_public_network_access = "Disabled"
    models_public_network_access  = "Disabled"
  }
  expect_failures = [var.gateway_public_network_access, var.models_public_network_access]
}

run "additional_private_hosted_agent" {
  command = plan
  variables {
    location                      = "swedencentral"
    enable_private_networking     = true
    enable_private_hosted_agent   = true
    gateway_public_network_access = "Disabled"
    models_public_network_access  = "Disabled"
    developer_principal_id        = "00000000-0000-0000-0000-000000000005"
  }
  override_resource {
    target          = azapi_resource.private_subnet["agents"]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway/providers/Microsoft.Network/virtualNetworks/test/subnets/agents"
    }
  }
  override_resource {
    target          = azapi_resource.private_agents[0]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway/providers/Microsoft.CognitiveServices/accounts/private-agents"
    }
  }
  override_resource {
    target          = azapi_resource.private_project[0]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway/providers/Microsoft.CognitiveServices/accounts/private-agents/projects/private"
      identity = {
        type         = "SystemAssigned"
        principal_id = "00000000-0000-0000-0000-000000000006"
        tenant_id    = "00000000-0000-0000-0000-000000000007"
      }
    }
  }
  assert {
    condition = (
      azapi_resource.agents.body.properties.publicNetworkAccess == "Enabled" &&
      !can(azapi_resource.agents.body.properties.networkInjections) &&
      azapi_resource.project.name == local.names.project &&
      output.project_endpoint == "https://${local.names.agents}.services.ai.azure.com/api/projects/${local.names.project}" &&
      azapi_resource.registry.body.properties.publicNetworkAccess == "Enabled" &&
      length(azapi_resource.model_deployment) == 1
    )
    error_message = "The opt-in extension must retain the original account/project, registry access, compatibility output and existing models."
  }
  assert {
    condition = (
      azapi_resource.private_agents[0].name != azapi_resource.agents.name &&
      azapi_resource.private_agents[0].body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.private_agents[0].body.properties.disableLocalAuth &&
      azapi_resource.private_agents[0].body.properties.networkAcls.defaultAction == "Deny" &&
      azapi_resource.private_agents[0].body.properties.networkInjections[0].scenario == "agent" &&
      !azapi_resource.private_agents[0].body.properties.networkInjections[0].useMicrosoftManagedNetwork &&
      azapi_resource.private_agents[0].body.properties.networkInjections[0].subnetArmId == azapi_resource.private_subnet["agents"].id
    )
    error_message = "The new account must be private and Entra-only with BYO agent injection in its creation body."
  }
  assert {
    condition = (
      length(azapi_resource.private_subnet) == 4 &&
      azapi_resource.private_subnet["agents"].body.properties.addressPrefix == "10.247.3.0/24" &&
      azapi_resource.private_subnet["agents"].body.properties.delegations[0].properties.serviceName == "Microsoft.App/environments" &&
      azapi_resource.private_subnet["gateway"].body.properties.delegations[0].properties.serviceName == "Microsoft.Web/serverFarms" &&
      length(azapi_resource.private_nsg["agents"].body.properties.securityRules) == 4 &&
      length(azapi_resource.private_endpoint) == 2 &&
      length(azapi_resource.private_agent_endpoint) == 2 &&
      length(azapi_resource.private_dns_zone) == 5 &&
      azapi_resource.private_agent_endpoint["agents"].body.properties.privateLinkServiceConnections[0].properties.groupIds[0] == "account" &&
      azapi_resource.private_agent_endpoint["registry"].body.properties.privateLinkServiceConnections[0].properties.groupIds[0] == "registry" &&
      local.private_dns_zones.registry == "privatelink.azurecr.io"
    )
    error_message = "Use a dedicated agent subnet, retain gateway delegation and add only the Foundry/registry private paths."
  }
  assert {
    condition = (
      length(azapi_resource.private_project_capability_host[0].body.properties) == 1 &&
      azapi_resource.private_project_capability_host[0].body.properties.capabilityHostKind == "Agents" &&
      length(azapi_resource.private_agent_role_assignment) == 3 &&
      azapi_resource.private_agent_role_assignment["developer-project"].parent_id == azapi_resource.private_project[0].id &&
      azapi_resource.private_agent_role_assignment["developer-account-reader"].parent_id == azapi_resource.private_agents[0].id &&
      azapi_resource.private_registry_connection[0].body.properties.credentials.clientId == "00000000-0000-0000-0000-000000000006" &&
      length(azapi_resource.private_agent_key_binding) == 0 &&
      !output.private_hosted_agent.runtime_key_binding_configured &&
      azapi_resource.private_agent_key_role[0].body.properties.permissions[0].actions[0] == "Microsoft.ApiManagement/service/apiKeys/listSecrets/action"
    )
    error_message = "Use Basic platform-managed data, scoped roles, the new project registry identity and no placeholder runtime key binding."
  }
}

run "private_agent_runtime_reuses_existing_key_role" {
  command = plan
  variables {
    location                                  = "swedencentral"
    enable_private_networking                 = true
    enable_private_hosted_agent               = true
    enable_private_test_client                = true
    private_test_client_ssh_public_key        = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleOnlyNotForDeployment"
    private_hosted_agent_runtime_principal_id = "00000000-0000-0000-0000-000000000008"
  }
  override_resource {
    target          = azapi_resource.private_test_key_role[0]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/providers/Microsoft.Authorization/roleDefinitions/00000000-0000-0000-0000-000000000009"
    }
  }
  override_resource {
    target          = azapi_resource.gateway
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway/providers/Microsoft.ApiManagement/service/gateway"
      output = {
        properties = { gatewayUrl = "https://gateway.azure-api.net" }
      }
    }
  }
  assert {
    condition = (
      length(azapi_resource.private_agent_key_role) == 0 &&
      length(azapi_resource.private_agent_key_binding) == 1 &&
      azapi_resource.private_agent_key_binding[0].parent_id == azapi_resource.gateway.id &&
      azapi_resource.private_agent_key_binding[0].body.properties.roleDefinitionId == azapi_resource.private_test_key_role[0].id &&
      azapi_resource.private_agent_key_binding[0].body.properties.principalId == var.private_hosted_agent_runtime_principal_id &&
      azapi_resource.private_agent_key_binding[0].body.properties.principalType == "ServicePrincipal" &&
      output.private_hosted_agent.runtime_key_binding_configured
    )
    error_message = "Only bind the supplied runtime identity at gateway scope, reusing the existing narrow key-reader role."
  }
  assert {
    condition = (
      azapi_resource.private_agent_key_binding[0].name == uuidv5("url", "${azapi_resource.gateway.id}/${var.private_hosted_agent_runtime_principal_id}/${azapi_resource.private_test_key_role[0].name}") &&
      azapi_resource.private_agent_key_binding[0].name != uuidv5("url", "${azapi_resource.gateway.id}/${var.private_hosted_agent_runtime_principal_id}/${uuidv5("url", "${azapi_resource.resource_group["gateway"].id}/private-agent-key-reader")}")
    )
    error_message = "Enabling the test VM must use a role-specific assignment identity distinct from the dedicated agent-role assignment."
  }
}

run "reject_private_agent_without_network" {
  command = plan
  variables {
    location                    = "swedencentral"
    enable_private_hosted_agent = true
  }

  expect_failures = [var.enable_private_hosted_agent]
}

run "private_agent_runtime_without_probe_vm" {
  command = plan
  variables {
    location                                  = "swedencentral"
    enable_private_networking                 = true
    enable_private_hosted_agent               = true
    private_hosted_agent_runtime_principal_id = "00000000-0000-0000-0000-000000000008"
    gateway_access_principals = {
      independent-caller = { principal_id = "00000000-0000-0000-0000-000000000009" }
    }
  }
  override_resource {
    target          = azapi_resource.private_agent_key_role[0]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/providers/Microsoft.Authorization/roleDefinitions/00000000-0000-0000-0000-000000000010"
    }
  }
  override_resource {
    target          = azapi_resource.gateway
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway/providers/Microsoft.ApiManagement/service/gateway"
      output = {
        properties = { gatewayUrl = "https://gateway.azure-api.net" }
      }
    }
  }
  assert {
    condition = (
      length(azapi_resource.private_test_key_role) == 0 &&
      length(azapi_resource.role_assignment) == 8 &&
      azapi_resource.runtime_api_key.name == "default" &&
      azapi_resource.role_assignment["gateway-models-user-independent-caller"].body.properties.principalId == var.gateway_access_principals["independent-caller"].principal_id &&
      length(azapi_resource.private_agent_role_assignment) == 1 &&
      length(azapi_resource.private_agent_key_role[0].body.properties.permissions[0].actions) == 1 &&
      length(azapi_resource.private_agent_key_role[0].body.properties.permissions[0].dataActions) == 0 &&
      azapi_resource.private_agent_key_binding[0].body.properties.roleDefinitionId == azapi_resource.private_agent_key_role[0].id &&
      output.private_hosted_agent.key_reader_role_definition_id == azapi_resource.private_agent_key_role[0].id
    )
    error_message = "Without a probe VM, use only the dedicated narrow runtime key role and omit optional developer grants."
  }
  assert {
    condition = (
      azapi_resource.private_agent_key_binding[0].name == uuidv5("url", "${azapi_resource.gateway.id}/${var.private_hosted_agent_runtime_principal_id}/${azapi_resource.private_agent_key_role[0].name}") &&
      azapi_resource.private_agent_key_binding[0].name != uuidv5("url", "${azapi_resource.gateway.id}/${var.private_hosted_agent_runtime_principal_id}/${uuidv5("url", "${azapi_resource.resource_group["gateway"].id}/private-test-key-reader")}") &&
      azapi_resource.private_agent_key_binding[0].parent_id == azapi_resource.gateway.id &&
      azapi_resource.private_agent_key_binding[0].body.properties.principalId == var.private_hosted_agent_runtime_principal_id
    )
    error_message = "Disabling the test VM must restore a distinct dedicated-role assignment while preserving gateway scope and runtime principal."
  }
}

run "reject_private_agent_region_mismatch" {
  command = plan
  variables {
    enable_private_networking   = true
    enable_private_hosted_agent = true
  }
  expect_failures = [var.enable_private_hosted_agent]
}

run "reject_private_agent_non_rfc1918" {
  command = plan
  variables {
    location                       = "swedencentral"
    enable_private_networking      = true
    enable_private_hosted_agent    = true
    private_network_address_prefix = "100.64.0.0/16"
  }
  expect_failures = [var.enable_private_hosted_agent]
}

run "reject_runtime_identity_without_private_agent" {
  command = plan
  variables {
    private_hosted_agent_runtime_principal_id = "00000000-0000-0000-0000-000000000008"
  }
  expect_failures = [var.private_hosted_agent_runtime_principal_id]
}

run "reject_malformed_runtime_identity" {
  command = plan
  variables {
    location                                  = "swedencentral"
    enable_private_networking                 = true
    enable_private_hosted_agent               = true
    private_hosted_agent_runtime_principal_id = "not-a-principal-id"
  }
  expect_failures = [var.private_hosted_agent_runtime_principal_id]
}

run "additive_gateway_entra_access" {
  command = plan
  variables {
    gateway_access_principals = {
      application = { principal_id = "00000000-0000-0000-0000-000000000002" }
      developer = {
        principal_id   = "00000000-0000-0000-0000-000000000003"
        principal_type = "User"
      }
      team = {
        principal_id   = "00000000-0000-0000-0000-000000000004"
        principal_type = "Group"
      }
    }
  }
  override_resource {
    target          = azapi_resource.gateway
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/shared-gateway/providers/Microsoft.ApiManagement/service/test"
      output = {
        properties = { gatewayUrl = "https://gateway.example" }
      }
    }
  }
  assert {
    condition = (
      length(azapi_resource.role_assignment) == 10 &&
      alltrue([for key, principal in var.gateway_access_principals :
        azapi_resource.role_assignment["gateway-models-user-${key}"].parent_id == azapi_resource.gateway.id &&
        azapi_resource.role_assignment["gateway-models-user-${key}"].body.properties.principalId == principal.principal_id &&
        azapi_resource.role_assignment["gateway-models-user-${key}"].body.properties.principalType == principal.principal_type &&
        azapi_resource.role_assignment["gateway-models-user-${key}"].body.properties.roleDefinitionId == "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/a6b68e3d-a1f0-4c60-8678-237c050cf4ea" &&
        azapi_resource.role_assignment["gateway-models-user-${key}"].name == uuidv5("url", "${azapi_resource.gateway.id}/${principal.principal_id}/a6b68e3d-a1f0-4c60-8678-237c050cf4ea")
      ]) &&
      azapi_resource.role_assignment["gateway-models-user-application"].body.properties.principalType == "ServicePrincipal" &&
      azapi_resource.runtime_api_key.name == "default" &&
      azapi_resource.gateway.body.properties.publicNetworkAccess == "Enabled"
    )
    error_message = "Entra caller bindings must be deterministic gateway-scoped model-invocation grants for the supplied identities, without changing API keys, networking or backend roles."
  }
}

run "reject_invalid_gateway_caller_id" {
  command = plan
  variables {
    gateway_access_principals = { caller = { principal_id = "not-an-object-id" } }
  }
  expect_failures = [var.gateway_access_principals]
}

run "reject_invalid_gateway_caller_type" {
  command = plan
  variables {
    gateway_access_principals = {
      caller = {
        principal_id   = "00000000-0000-0000-0000-000000000002"
        principal_type = "Application"
      }
    }
  }
  expect_failures = [var.gateway_access_principals]
}

run "reject_duplicate_gateway_callers" {
  command = plan
  variables {
    gateway_access_principals = {
      first  = { principal_id = "aaaaaaaa-0000-0000-0000-000000000002" }
      second = { principal_id = "AAAAAAAA-0000-0000-0000-000000000002" }
    }
  }
  expect_failures = [var.gateway_access_principals]
}
