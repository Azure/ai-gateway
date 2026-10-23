output "resource_group_name" {
  description = "Single shared resource group for gateway, Foundry, monitoring and optional networking."
  value       = azapi_resource.resource_group["gateway"].name
}

output "resource_groups" {
  description = "Compatibility aliases: gateway, models and agents all refer to the same shared resource group."
  value       = { for key in ["gateway", "models", "agents"] : key => azapi_resource.resource_group["gateway"].name }
}

output "gateway_id" {
  description = "ARM resource ID of the AIGateway service."
  value       = azapi_resource.gateway.id
}

output "gateway_endpoint" {
  description = "Runtime endpoint returned by the gateway service."
  value       = azapi_resource.gateway.output.properties.gatewayUrl
}

output "gateway_api_key_id" {
  description = "API key resource ID only; no runtime key value is exported."
  value       = azapi_resource.runtime_api_key.id
}

output "model_deployment_ids" {
  description = "Model deployment ARM IDs keyed by the names registered in the gateway."
  value       = { for key, deployment in azapi_resource.model_deployment : key => deployment.id }
}

output "model_api_configuration" {
  description = "Non-secret API metadata used to check compatibility before running the sample's chat-completions probes."
  value = { for key, model in var.model_deployments : key => {
    api_format = model.api_format
    endpoints  = model.endpoints
  } }
}

output "foundry_models_id" {
  description = "Dedicated Foundry model account ARM ID."
  value       = azapi_resource.models.id
}

output "project_id" {
  description = "Foundry hosted-agent project ARM ID."
  value       = azapi_resource.project.id
}

output "project_endpoint" {
  description = "Foundry project data-plane endpoint."
  value       = "https://${local.names.agents}.services.ai.azure.com/api/projects/${local.names.project}"
}

output "container_registry_endpoint" {
  description = "Registry login server for separately built hosted-agent images."
  value       = azapi_resource.registry.output.properties.loginServer
}

output "storage_account_name" {
  description = "Storage account for project artifacts."
  value       = azapi_resource.storage.name
}

output "application_insights_ids" {
  description = "Separate Application Insights resource IDs for gateway telemetry and agent tracing."
  value       = { for key, insights in azapi_resource.insights : key => insights.id }
}

output "private_endpoint_ids" {
  description = "Gateway and model private endpoint IDs when private networking is enabled."
  value       = { for key, endpoint in azapi_resource.private_endpoint : key => endpoint.id }
}

output "private_test_vm_id" {
  description = "Optional private test VM ID. Start/deallocate separately; power state is not Terraform configuration."
  value       = var.enable_private_test_client ? azapi_resource.private_test_vm[0].id : null
}

output "private_probe_configuration" {
  description = "Non-secret inputs for scripts/private-path-probe.py on the optional test VM."
  value = var.enable_private_test_client ? {
    gateway_id              = azapi_resource.gateway.id
    gateway_endpoint        = azapi_resource.gateway.output.properties.gatewayUrl
    model_endpoint          = azapi_resource.models.output.properties.endpoint
    model_names             = keys(var.model_deployments)
    private_endpoint_subnet = local.private_subnets["endpoints"]
  } : null
}
