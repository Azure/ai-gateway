locals {
  private_agent_name   = "${local.names.agents}-private"
  private_project_name = "${local.names.project}-private"
  private_agent_endpoints = var.enable_private_hosted_agent ? {
    agents = {
      resource_id = azapi_resource.private_agents[0].id
      group_id    = "account"
      dns_keys    = ["cognitiveservices", "openai", "services"]
    }
    registry = {
      resource_id = azapi_resource.registry.id
      group_id    = "registry"
      dns_keys    = ["registry"]
    }
  } : {}
  private_agent_roles = var.enable_private_hosted_agent ? merge({
    project-acr-pull = {
      scope          = azapi_resource.registry.id
      principal_id   = azapi_resource.private_project[0].identity[0].principal_id
      principal_type = "ServicePrincipal"
      role_id        = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
    }
    }, var.developer_principal_id == "" ? {} : {
    developer-project = {
      scope          = azapi_resource.private_project[0].id
      principal_id   = var.developer_principal_id
      principal_type = var.developer_principal_type
      role_id        = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
    }
    developer-account-reader = {
      scope          = azapi_resource.private_agents[0].id
      principal_id   = var.developer_principal_id
      principal_type = var.developer_principal_type
      role_id        = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
    }
  }) : {}
}

resource "azapi_resource" "private_agents" {
  count                 = var.enable_private_hosted_agent ? 1 : 0
  type                  = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                  = local.private_agent_name
  parent_id             = azapi_resource.resource_group["gateway"].id
  location              = var.location
  tags                  = local.tags
  replace_triggers_refs = ["properties.networkInjections", "properties.customSubDomainName"]
  identity { type = "SystemAssigned" }
  body = {
    kind = "AIServices"
    sku  = { name = "S0" }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = local.private_agent_name
      disableLocalAuth       = true
      publicNetworkAccess    = "Disabled"
      networkAcls = {
        defaultAction       = "Deny"
        virtualNetworkRules = []
        ipRules             = []
      }
      networkInjections = [{
        scenario                   = "agent"
        subnetArmId                = azapi_resource.private_subnet["agents"].id
        useMicrosoftManagedNetwork = false
      }]
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "azapi_resource" "private_project" {
  count     = var.enable_private_hosted_agent ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = local.private_project_name
  parent_id = azapi_resource.private_agents[0].id
  location  = var.location
  tags      = local.tags
  identity { type = "SystemAssigned" }
  body = {
    properties = {
      displayName = "${var.project_display_name} (private)"
      description = "Additional VNet-injected Basic project; use the existing private AI Gateway for models."
    }
  }
  depends_on = [azapi_resource.private_agent_dns_zone_group["agents"]]
}

# Separate collection keeps additions from deferring the legacy gateway approval read.
resource "azapi_resource" "private_agent_endpoint" {
  for_each              = local.private_agent_endpoints
  type                  = "Microsoft.Network/privateEndpoints@2024-05-01"
  name                  = "${local.names.gateway}-${each.key}-pe"
  parent_id             = azapi_resource.resource_group["gateway"].id
  location              = var.gateway_location
  tags                  = local.tags
  replace_triggers_refs = ["properties.privateLinkServiceConnections"]
  body = {
    properties = {
      subnet = { id = azapi_resource.private_subnet["endpoints"].id }
      privateLinkServiceConnections = [{
        name = each.key
        properties = {
          privateLinkServiceId = each.value.resource_id
          groupIds             = [each.value.group_id]
        }
      }]
    }
  }
}

resource "azapi_resource" "private_agent_dns_zone_group" {
  for_each  = local.private_agent_endpoints
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01"
  name      = "default"
  parent_id = azapi_resource.private_agent_endpoint[each.key].id
  body = {
    properties = {
      privateDnsZoneConfigs = [for key in each.value.dns_keys : {
        name       = key
        properties = { privateDnsZoneId = azapi_resource.private_dns_zone[key].id }
      }]
    }
  }
}

resource "azapi_resource" "private_project_capability_host" {
  # Foundry sample11 uses this field, absent from AzAPI 2.13's project-host schema.
  schema_validation_enabled = false
  count                     = var.enable_private_hosted_agent ? 1 : 0
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "caphostproj"
  parent_id                 = azapi_resource.private_project[0].id
  body = {
    properties = { capabilityHostKind = "Agents" }
  }
}

resource "azapi_resource" "private_agent_role_assignment" {
  for_each  = local.private_agent_roles
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5("url", "${each.value.scope}/${each.value.principal_id}/${each.value.role_id}")
  parent_id = each.value.scope
  body = {
    properties = {
      principalId      = each.value.principal_id
      principalType    = each.value.principal_type
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${each.value.role_id}"
    }
  }
}

resource "azapi_resource" "private_registry_connection" {
  count     = var.enable_private_hosted_agent ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name      = "${local.names.registry}-conn"
  parent_id = azapi_resource.private_project[0].id
  body = {
    properties = {
      category      = "ContainerRegistry"
      target        = azapi_resource.registry.output.properties.loginServer
      authType      = "ManagedIdentity"
      isSharedToAll = false
      credentials = {
        clientId   = azapi_resource.private_project[0].identity[0].principal_id
        resourceId = azapi_resource.registry.id
      }
      metadata = { ResourceId = azapi_resource.registry.id }
    }
  }
  depends_on = [
    azapi_resource.private_agent_role_assignment["project-acr-pull"],
    azapi_resource.private_agent_dns_zone_group["registry"]
  ]
}

resource "azapi_resource" "private_insights_connection" {
  count     = var.enable_private_hosted_agent ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  name      = azapi_resource.insights["agents"].name
  parent_id = azapi_resource.private_agents[0].id
  body = {
    properties = {
      category      = "AppInsights"
      authType      = "ApiKey"
      isSharedToAll = true
      target        = azapi_resource.insights["agents"].id
      credentials   = { key = azapi_resource.insights["agents"].output.properties.ConnectionString }
      metadata = {
        ApiType     = "Azure"
        ResourceId  = azapi_resource.insights["agents"].id
        displayName = azapi_resource.insights["agents"].name
      }
    }
  }
}

resource "azapi_resource" "private_agent_key_role" {
  count     = var.enable_private_hosted_agent && !var.enable_private_test_client ? 1 : 0
  type      = "Microsoft.Authorization/roleDefinitions@2022-04-01"
  name      = uuidv5("url", "${azapi_resource.resource_group["gateway"].id}/private-agent-key-reader")
  parent_id = local.subscription_scope
  body = {
    properties = {
      roleName         = "AI Gateway private agent key reader ${local.resource_token}"
      description      = "Retrieve gateway runtime keys for the separately deployed private hosted agent."
      type             = "CustomRole"
      assignableScopes = [azapi_resource.resource_group["gateway"].id]
      permissions = [{
        actions        = ["Microsoft.ApiManagement/service/apiKeys/listSecrets/action"]
        notActions     = []
        dataActions    = []
        notDataActions = []
      }]
    }
  }
}

resource "azapi_resource" "private_agent_key_binding" {
  count = var.enable_private_hosted_agent && var.private_hosted_agent_runtime_principal_id != "" ? 1 : 0
  type  = "Microsoft.Authorization/roleAssignments@2022-04-01"
  # A role change must replace the assignment, not update its immutable roleDefinitionId.
  name      = uuidv5("url", "${azapi_resource.gateway.id}/${var.private_hosted_agent_runtime_principal_id}/${var.enable_private_test_client ? azapi_resource.private_test_key_role[0].name : azapi_resource.private_agent_key_role[0].name}")
  parent_id = azapi_resource.gateway.id
  body = {
    properties = {
      principalId      = var.private_hosted_agent_runtime_principal_id
      principalType    = "ServicePrincipal"
      roleDefinitionId = var.enable_private_test_client ? azapi_resource.private_test_key_role[0].id : azapi_resource.private_agent_key_role[0].id
    }
  }
}
