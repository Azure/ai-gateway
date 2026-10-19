locals {
  subscription_scope = "/subscriptions/${var.subscription_id}"
  resource_token     = substr(sha256("${var.subscription_id}:${var.environment_name}:${var.location}"), 0, 12)
  tags               = merge(var.tags, { environment = var.environment_name })
  names = {
    gateway  = "aigw-${local.resource_token}"
    models   = "aimodels-${local.resource_token}"
    agents   = "aiagents-${local.resource_token}"
    project  = "proj-${local.resource_token}"
    storage  = "st${local.resource_token}"
    registry = "acr${local.resource_token}"
  }
}

resource "azapi_resource" "resource_group" {
  for_each  = toset(["gateway", "models", "agents"])
  type      = "Microsoft.Resources/resourceGroups@2021-04-01"
  name      = "rg-${var.environment_name}-${local.resource_token}-${each.key}"
  parent_id = local.subscription_scope
  location  = var.location
  tags      = local.tags
  body      = { properties = {} }
}

resource "azapi_resource" "logs" {
  for_each  = toset(["gateway", "agents"])
  type      = "Microsoft.OperationalInsights/workspaces@2023-09-01"
  name      = "${local.names[each.key]}-logs"
  parent_id = azapi_resource.resource_group[each.key].id
  location  = var.location
  tags      = local.tags
  body = {
    properties = {
      retentionInDays = 30
      features        = { enableLogAccessUsingOnlyResourcePermissions = true }
      sku             = { name = "PerGB2018" }
    }
  }
}

resource "azapi_resource" "insights" {
  for_each  = toset(["gateway", "agents"])
  type      = "Microsoft.Insights/components@2020-02-02"
  name      = "${local.names[each.key]}-insights"
  parent_id = azapi_resource.resource_group[each.key].id
  location  = var.location
  tags      = local.tags
  body = {
    kind = "web"
    properties = {
      Application_Type    = "web"
      IngestionMode       = "LogAnalytics"
      WorkspaceResourceId = azapi_resource.logs[each.key].id
    }
  }
  response_export_values = ["properties.ConnectionString"]
}
