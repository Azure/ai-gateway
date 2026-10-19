mock_provider "azapi" {}

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
      length(azapi_resource.role_assignment) == 6 &&
      length(azapi_resource.private_endpoint) == 0 &&
      length(azapi_resource.private_test_vm) == 0 &&
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
      length(azapi_resource.role_assignment) == 13 &&
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
    enable_private_networking     = jsondecode(file("profiles/private-connectivity.tfvars.json")).enable_private_networking
    gateway_public_network_access = jsondecode(file("profiles/private-connectivity.tfvars.json")).gateway_public_network_access
    models_public_network_access  = jsondecode(file("profiles/private-connectivity.tfvars.json")).models_public_network_access
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
    error_message = "The PoC profile must retain AIGateway, outbound integration and private models without requesting blocked private-only ingress."
  }

  assert {
    condition = (
      length(azapi_resource.private_endpoint) == 2 &&
      length(azapi_resource.private_dns_zone) == 4 &&
      azapi_resource.private_endpoint["gateway"].body.properties.privateLinkServiceConnections[0].properties.privateLinkServiceId == azapi_resource.gateway.id &&
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
      azapi_resource.telemetry_exporter.body.properties.kind == "applicationInsights" &&
      !azapi_resource.telemetry_exporter.body.properties.payloadCapture
    )
    error_message = "The profile must retain gateway API-key provisioning and workspace telemetry without payload capture."
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

run "reject_public_disable_without_network" {
  command = plan
  variables {
    gateway_public_network_access = "Disabled"
    models_public_network_access  = "Disabled"
  }
  expect_failures = [var.gateway_public_network_access, var.models_public_network_access]
}
