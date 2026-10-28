// Lab 13 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then the Application Insights destination for the gateway's telemetry,
// and connects the gateway to it over OpenTelemetry. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. During the preview, AI Gateway runs in East US 2 and Sweden Central.')
@allowed([
  'eastus2'
  'swedencentral'
])
@metadata({ azd: { type: 'location' } })
param location string

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, a Foundry model behind the default alias, and the app-first-call key.
module base '../../quickstart/infra/resources.bicep' = {
  name: 'aigw-base'
  scope: rg
  params: {
    location: location
    tags: tags
    gatewayName: 'aigw-${suffix}'
    foundryName: 'aigw${suffix}'
  }
}

// The destination: a Log Analytics workspace and an Application Insights component with OTLP ingestion on.
module monitoring 'monitoring.bicep' = {
  name: 'aigw-monitoring'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    location: location
    tags: tags
    enableOtlpIngestion: true
  }
}

// What the portal's Configure telemetry wizard does next: an OpenTelemetry exporter with the recommended token claims.
// azure.yaml then grants the gateway's identity Monitoring Metrics Publisher on the data collection rule.
module telemetry 'otel-exporter.bicep' = {
  name: 'aigw-telemetry'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    appInsightsName: monitoring.outputs.appInsightsName
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = base.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
output APP_INSIGHTS_NAME string = monitoring.outputs.appInsightsName
output LOG_ANALYTICS_WORKSPACE_ID string = monitoring.outputs.logAnalyticsWorkspaceId
output LOG_ANALYTICS_CUSTOMER_ID string = monitoring.outputs.logAnalyticsCustomerId
output TELEMETRY_EXPORTER_NAME string = telemetry.outputs.telemetryExporterName
output AI_GATEWAY_PRINCIPAL_ID string = telemetry.outputs.gatewayPrincipalId
output DATA_COLLECTION_RULE_ID string = telemetry.outputs.dataCollectionRuleId
