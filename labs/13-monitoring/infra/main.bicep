// Creates the Application Insights destination for AI Gateway telemetry with the same resource shapes as the
// reference sample (Azure-Samples/simple-foundry-hosted-agent-python-aigateway, infra/ai-gateway/main.bicep):
// a Log Analytics workspace and a workspace-based Application Insights component.
//
// After you deploy it, connect the gateway in the portal: Monitoring › Configure telemetry ›
// Existing Azure Application Insights resource. The portal enables OTLP ingestion on the component, grants the
// gateway's managed identity the Monitoring Metrics Publisher role, and creates an OpenTelemetry exporter.

@description('Name of the existing AI Gateway (API Management service with the AIGateway SKU).')
param gatewayName string

@description('Location for the monitoring resources.')
param location string = resourceGroup().location

@description('Application Insights component name. The portal suggests <gateway>-insights for new destinations.')
param appInsightsName string = '${gatewayName}-insights'

@description('Log Analytics workspace that stores the OTelSpans and OTelLogs tables.')
param logAnalyticsWorkspaceName string = take('${gatewayName}-logs', 63)

@description('Tags applied to the monitoring resources.')
param tags object = {}

@description('Also create the sample\'s telemetry exporter (kind applicationInsights). The portal flags this kind as legacy because it no longer activates OTLP signals. Leave false and connect in the portal.')
param deployLegacyExporter bool = false

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
  }
}

resource gateway 'Microsoft.ApiManagement/service@2025-09-01-preview' existing = {
  name: gatewayName
}

resource defaultWorkspace 'Microsoft.ApiManagement/service/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

// The reference sample's exporter, unchanged. Kept for reference only: see deployLegacyExporter.
resource telemetryExporter 'Microsoft.ApiManagement/service/workspaces/telemetryExporters@2025-09-01-preview' = if (deployLegacyExporter) {
  parent: defaultWorkspace
  name: 'appinsights'
  properties: {
    kind: 'applicationInsights'
    payloadCapture: false
    applicationInsights: {
      connectionString: appInsights.properties.ConnectionString
      resourceId: appInsights.id
    }
  }
}

output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
output logAnalyticsWorkspaceName string = logAnalyticsWorkspace.name
