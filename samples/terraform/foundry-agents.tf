resource "azapi_resource" "agents" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.names.agents
  parent_id = azapi_resource.resource_group["agents"].id
  location  = var.location
  tags      = local.tags
  identity { type = "SystemAssigned" }
  body = {
    kind = "AIServices"
    sku  = { name = "S0" }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = local.names.agents
      disableLocalAuth       = true
      publicNetworkAccess    = "Enabled"
      networkAcls = {
        defaultAction       = "Allow"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }
}

resource "azapi_resource" "storage" {
  type      = "Microsoft.Storage/storageAccounts@2024-01-01"
  name      = local.names.storage
  parent_id = azapi_resource.resource_group["agents"].id
  location  = var.location
  tags      = local.tags
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_LRS" }
    properties = {
      minimumTlsVersion     = "TLS1_2"
      allowBlobPublicAccess = false
      allowSharedKeyAccess  = false
      publicNetworkAccess   = var.storage_public_network_access
      networkAcls = {
        bypass              = "AzureServices"
        defaultAction       = "Allow"
        virtualNetworkRules = []
      }
    }
  }
  response_export_values = ["properties.primaryEndpoints.blob"]
}

resource "azapi_resource" "registry" {
  type      = "Microsoft.ContainerRegistry/registries@2023-07-01"
  name      = local.names.registry
  parent_id = azapi_resource.resource_group["agents"].id
  location  = var.location
  tags      = local.tags
  identity { type = "SystemAssigned" }
  body = {
    sku = { name = "Premium" }
    properties = {
      adminUserEnabled    = false
      publicNetworkAccess = "Enabled"
      zoneRedundancy      = "Disabled"
    }
  }
  response_export_values = ["properties.loginServer"]
}

resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = local.names.project
  parent_id = azapi_resource.agents.id
  location  = var.location
  tags      = local.tags
  identity { type = "SystemAssigned" }
  body = {
    properties = {
      displayName = var.project_display_name
      description = var.project_description
    }
  }
}

resource "azapi_resource" "storage_connection" {
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name      = local.names.storage
  parent_id = azapi_resource.project.id
  body = {
    properties = {
      category = "AzureStorageAccount"
      target   = azapi_resource.storage.output.properties.primaryEndpoints.blob
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azapi_resource.storage.id
        location   = var.location
      }
    }
  }
  depends_on = [azapi_resource.role_assignment["project-storage"]]
}

resource "azapi_resource" "registry_connection" {
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name      = "${local.names.registry}-conn"
  parent_id = azapi_resource.project.id
  body = {
    properties = {
      category      = "ContainerRegistry"
      target        = azapi_resource.registry.output.properties.loginServer
      authType      = "ManagedIdentity"
      isSharedToAll = false
      credentials = {
        clientId   = azapi_resource.project.identity[0].principal_id
        resourceId = azapi_resource.registry.id
      }
      metadata = { ResourceId = azapi_resource.registry.id }
    }
  }
  depends_on = [azapi_resource.role_assignment["project-acr-pull"]]
}

resource "azapi_resource" "insights_connection" {
  type      = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  name      = azapi_resource.insights["agents"].name
  parent_id = azapi_resource.agents.id
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
