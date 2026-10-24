resource "azapi_resource" "gateway" {
  type      = "Microsoft.ApiManagement/service@2025-09-01-preview"
  name      = local.names.gateway
  parent_id = azapi_resource.resource_group["gateway"].id
  location  = var.gateway_location
  tags      = local.tags
  identity { type = "SystemAssigned" }
  body = {
    sku = { name = "AIGateway", capacity = 1 }
    properties = {
      publisherEmail      = var.publisher_email
      publisherName       = var.publisher_name
      publicNetworkAccess = var.gateway_public_network_access
      virtualNetworkType  = var.enable_private_networking ? "External" : "None"
      virtualNetworkConfiguration = var.enable_private_networking ? {
        subnetResourceId = azapi_resource.private_subnet["gateway"].id
      } : null
    }
  }
  response_export_values = ["properties.gatewayUrl"]
  lifecycle {
    prevent_destroy = true
  }
  timeouts {
    create = "60m"
    update = "60m"
    delete = "60m"
  }
  depends_on = [azapi_resource.private_dns_link]
}

resource "azapi_resource" "connector_gateway" {
  # This preview type is not yet present in AzAPI's bundled schema.
  schema_validation_enabled = false
  type                      = "Microsoft.Web/connectorGateways@2026-05-01-preview"
  name                      = local.names.gateway
  parent_id                 = azapi_resource.resource_group["gateway"].id
  location                  = var.gateway_location
  body                      = { properties = {} }
  depends_on                = [azapi_resource.gateway]
}

locals {
  # The AIGateway service creates its default workspace; do not manage it twice.
  gateway_workspace_id = "${azapi_resource.gateway.id}/workspaces/default"
  gateway_monitoring = {
    dcr_id = try(coalesce(
      try(azapi_resource.insights["gateway"].output.properties.DataCollectionRuleResourceId, null),
      try(azapi_resource.insights["gateway"].output.properties.DataCollectionRuleId, null)
    ), "")
    metrics_endpoint = try(coalesce(azapi_resource.insights["gateway"].output.properties.OTLPMetricsEndpoint), "")
    logs_endpoint    = try(coalesce(azapi_resource.insights["gateway"].output.properties.OTLPLogsEndpoint), "")
    traces_endpoint  = try(coalesce(azapi_resource.insights["gateway"].output.properties.OTLPTracesEndpoint), "")
  }
}

resource "azapi_resource" "telemetry_exporter" {
  # This preview type is not yet present in AzAPI's bundled schema.
  schema_validation_enabled = false
  type                      = "Microsoft.ApiManagement/service/workspaces/telemetryExporters@2025-09-01-preview"
  name                      = "appinsights"
  parent_id                 = local.gateway_workspace_id
  body = {
    properties = {
      kind           = "OpenTelemetry"
      payloadCapture = false
      applicationInsights = {
        resourceId = azapi_resource.insights["gateway"].id
      }
      openTelemetry = {
        metricsEndpoint = local.gateway_monitoring.metrics_endpoint
        logsEndpoint    = local.gateway_monitoring.logs_endpoint
        tracesEndpoint  = local.gateway_monitoring.traces_endpoint
        credentials = {
          managedIdentity = { resource = "https://monitor.azure.com" }
        }
      }
    }
  }
  lifecycle {
    precondition {
      condition = alltrue([
        for endpoint in [
          local.gateway_monitoring.metrics_endpoint,
          local.gateway_monitoring.logs_endpoint,
          local.gateway_monitoring.traces_endpoint
        ] : can(regex("^https://[^/?#]+/[^?#]+$", endpoint))
      ])
      error_message = "Gateway OTLP endpoints are incomplete. Enable gateway Insights first, run scripts/Get-GatewayMonitoring.ps1, then create a fresh plan; see docs/monitoring.md."
    }
  }
  depends_on = [azapi_resource.role_assignment["gateway-monitoring-publisher"]]
}

resource "azapi_resource" "foundry_provider" {
  # This preview type is not yet present in AzAPI's bundled schema.
  schema_validation_enabled = false
  type                      = "Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview"
  name                      = "foundry"
  parent_id                 = local.gateway_workspace_id
  body = {
    properties = {
      kind        = "Foundry"
      displayName = "Foundry"
      description = "Managed-identity access to the dedicated Foundry model account."
      foundry = {
        endpoint    = "${trimsuffix(azapi_resource.models.output.properties.endpoint, "/")}/"
        resourceIds = [azapi_resource.models.id]
        authentication = {
          kind            = "ManagedIdentity"
          managedIdentity = { resource = "https://cognitiveservices.azure.com/" }
        }
      }
    }
  }
  depends_on = [azapi_resource.role_assignment["gateway-foundry-user"]]
}

resource "azapi_resource" "catalog_model" {
  # This preview type is not yet present in AzAPI's bundled schema.
  schema_validation_enabled = false
  for_each                  = var.model_deployments
  type                      = "Microsoft.ApiManagement/service/workspaces/modelProviders/models@2025-09-01-preview"
  name                      = each.key
  parent_id                 = azapi_resource.foundry_provider.id
  body = {
    properties = {
      description        = each.value.description
      displayName        = each.value.model_name
      apiFormat          = each.value.api_format
      supportedEndpoints = each.value.endpoints
      deployment = {
        resourceId   = azapi_resource.model_deployment[each.key].id
        modelName    = each.key
        modelVersion = each.value.model_version
      }
      policies = [{
        type       = "tokenLimit"
        period     = "minute"
        count      = each.value.token_limit
        counterKey = ["identity"]
      }]
    }
  }
}

resource "azapi_resource" "model_alias" {
  # Runtime routing requires an alias in addition to the provider's catalog entry.
  schema_validation_enabled = false
  for_each                  = var.model_deployments
  type                      = "Microsoft.ApiManagement/service/workspaces/aliases@2025-09-01-preview"
  name                      = each.key
  parent_id                 = local.gateway_workspace_id
  body = {
    properties = {
      aliasName   = each.key
      description = each.value.description
      backendModels = [{
        resourceId = azapi_resource.catalog_model[each.key].id
      }]
    }
  }
}

resource "azapi_resource" "runtime_api_key" {
  # This preview type is not yet present in AzAPI's bundled schema.
  schema_validation_enabled = false
  type                      = "Microsoft.ApiManagement/service/apiKeys@2025-09-01-preview"
  name                      = "default"
  parent_id                 = azapi_resource.gateway.id
  body                      = { properties = { displayName = "All APIs subscription" } }
  response_export_values    = []
}
