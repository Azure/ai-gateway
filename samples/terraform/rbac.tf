locals {
  cognitive_roles = {
    contributor = "25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68"
    openai-user = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
    user        = "a97b65f3-24c7-4388-baec-2e87135dc908"
  }
  role_bindings = merge(
    {
      gateway-foundry-user = {
        scope          = azapi_resource.models.id
        principal_id   = azapi_resource.gateway.identity[0].principal_id
        principal_type = "ServicePrincipal"
        role_id        = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
      }
      gateway-monitoring-publisher = {
        scope          = local.gateway_monitoring.dcr_id
        principal_id   = azapi_resource.gateway.identity[0].principal_id
        principal_type = "ServicePrincipal"
        role_id        = "3913510d-42f4-4e42-8a64-420c390055eb"
      }
      project-storage = {
        scope          = azapi_resource.storage.id
        principal_id   = azapi_resource.project.identity[0].principal_id
        principal_type = "ServicePrincipal"
        role_id        = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
      }
      project-acr-pull = {
        scope          = azapi_resource.registry.id
        principal_id   = azapi_resource.project.identity[0].principal_id
        principal_type = "ServicePrincipal"
        role_id        = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
      }
    },
    { for key, role in local.cognitive_roles : "project-${key}" => {
      scope          = azapi_resource.agents.id
      principal_id   = azapi_resource.project.identity[0].principal_id
      principal_type = "ServicePrincipal"
      role_id        = role
    } },
    var.developer_principal_id == "" ? {} : merge(
      { for pair in setproduct(["models", "agents"], keys(local.cognitive_roles)) : "developer-${pair[0]}-${pair[1]}" => {
        scope          = pair[0] == "models" ? azapi_resource.models.id : azapi_resource.agents.id
        principal_id   = var.developer_principal_id
        principal_type = var.developer_principal_type
        role_id        = local.cognitive_roles[pair[1]]
      } },
      { developer-storage = {
        scope          = azapi_resource.storage.id
        principal_id   = var.developer_principal_id
        principal_type = var.developer_principal_type
        role_id        = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
      } }
    )
  )
}

resource "azapi_resource" "role_assignment" {
  for_each  = local.role_bindings
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
  lifecycle {
    precondition {
      condition = each.key != "gateway-monitoring-publisher" || can(regex(
        "(?i)^/subscriptions/${var.subscription_id}/resourceGroups/[^/?#]+/providers/Microsoft.Insights/dataCollectionRules/[^/?#]+$",
        each.value.scope
      ))
      error_message = "Gateway publishing requires the actual same-subscription OTLP DCR resource ID from Insights. Missing/immutable-only linkage must be resolved before applying; never substitute a group/subscription scope."
    }
  }
}
