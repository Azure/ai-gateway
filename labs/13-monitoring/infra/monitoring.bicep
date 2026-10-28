// Creates the Application Insights destination for AI Gateway telemetry: a Log Analytics workspace and a
// workspace-based Application Insights component.
//
// The lab's main.bicep calls it with azd, sets enableOtlpIngestion, and then connects the gateway with
// otel-exporter.bicep. You can also deploy it on its own to the resource group of an existing gateway, then connect
// the gateway in the portal: Monitoring › Configure telemetry › Existing Azure Application Insights resource. The
// portal enables OTLP ingestion on the component, grants the gateway's managed identity the Monitoring Metrics
// Publisher role, and creates an OpenTelemetry exporter.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
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

@description('Turn on OTLP ingestion on the component, as the portal does when you connect it. Azure then creates a managed Azure Monitor workspace, data collection endpoint, and data collection rule, and the component reports its OTLP endpoints.')
param enableOtlpIngestion bool = false

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
  // AzureMonitorWorkspaceIngestionMode isn't in the Bicep types for this API version yet, so union() adds it.
  properties: union(
    {
      Application_Type: 'web'
      WorkspaceResourceId: logAnalyticsWorkspace.id
    },
    enableOtlpIngestion ? { AzureMonitorWorkspaceIngestionMode: 'Enabled' } : {}
  )
}

// Read-only properties that the component reports once OTLP ingestion is on. any() skips the missing Bicep types.
var otlp = any(appInsights.properties)

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

// The reference sample's exporter, unchanged. Kept for reference only: see deployLegacyExporter.
#disable-next-line BCP081
resource telemetryExporter 'Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2025-09-01-preview' = if (deployLegacyExporter) {
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
output logAnalyticsCustomerId string = logAnalyticsWorkspace.properties.customerId
output dataCollectionRuleId string = otlp.?DataCollectionRuleResourceId ?? ''
output otlpMetricsEndpoint string = otlp.?OTLPMetricsEndpoint ?? ''
output otlpLogsEndpoint string = otlp.?OTLPLogsEndpoint ?? ''
output otlpTracesEndpoint string = otlp.?OTLPTracesEndpoint ?? ''
