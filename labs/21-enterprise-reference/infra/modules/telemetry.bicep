// The reference sample's gateway telemetry exporter, unchanged: kind applicationInsights, pointing at the
// Application Insights component from monitoring.bicep. The current AI Gateway portal labels this exporter kind as
// legacy ("This legacy exporter no longer activates OTLP signals"), so main.bicep only deploys this module when
// enableLegacyAppInsightsExporter is true. By default you connect the same component once in the portal instead:
// Monitoring › Configure telemetry › Existing Azure Application Insights resource.
targetScope = 'resourceGroup'

@description('Name of the existing gateway in this resource group.')
param gatewayName string

@description('Name of the existing Application Insights component in this resource group.')
param appInsightsName string

@description('Name of the telemetry exporter.')
param exporterName string = 'appinsights'

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

#disable-next-line BCP081
resource telemetryExporter 'Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: exporterName
  properties: {
    kind: 'applicationInsights'
    payloadCapture: false
    applicationInsights: {
      connectionString: appInsights.properties.ConnectionString
      resourceId: appInsights.id
    }
  }
}

output telemetryExporterId string = telemetryExporter.id
