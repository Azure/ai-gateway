// Connects an AI Gateway to Application Insights over OpenTelemetry, the same way the portal's Configure telemetry
// wizard does: an OpenTelemetry exporter that sends metrics, logs, and traces to the component's OTLP endpoints, with
// the token claims to add to the telemetry.
// Turn on OTLP ingestion on the component first (monitoring.bicep with enableOtlpIngestion=true): it creates the
// data collection rule and the endpoints. The gateway's system-assigned identity also needs Monitoring Metrics
// Publisher on that rule. Azure keeps the rule in a managed resource group whose deny assignment blocks deployments,
// so Bicep can't assign it: the lab's azure.yaml does it with the Azure CLI after "azd provision", using the
// gatewayPrincipalId and dataCollectionRuleId outputs. The lab's main.bicep calls this file with azd. You can also
// deploy it on its own to the resource group of an existing gateway and component, then assign the role yourself.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Application Insights component in this resource group, with OTLP ingestion on.')
param appInsightsName string

@description('Name of the telemetry exporter. The portal names it appinsights.')
param exporterName string = 'appinsights'

@description('Token claims to add to the telemetry, and the signals that carry each one. The default is the portal\'s "Include recommended token claims in telemetry".')
param claimAttributes array = [
  {
    source: { kind: 'claims', value: 'tid' }
    signals: ['logs', 'traces', 'metrics']
  }
  {
    source: { kind: 'claims', value: 'oid' }
    signals: ['logs', 'traces', 'metrics']
  }
  {
    source: { kind: 'claims', value: 'appid' }
    signals: ['logs', 'traces']
  }
  {
    source: { kind: 'claims', value: 'azp' }
    signals: ['logs', 'traces']
  }
]

@description('Log request and response payloads. Off by default: prompts and responses can be sensitive and add volume.')
param payloadCapture bool = false

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

// The OTLP properties aren't in the Bicep types for this API version yet. any() skips the type check.
var otlp = any(appInsights.properties)

#disable-next-line BCP081
resource telemetryExporter 'Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: exporterName
  properties: {
    kind: 'OpenTelemetry'
    payloadCapture: payloadCapture
    applicationInsights: {
      resourceId: appInsights.id
    }
    openTelemetry: {
      metricsEndpoint: otlp.OTLPMetricsEndpoint
      logsEndpoint: otlp.OTLPLogsEndpoint
      tracesEndpoint: otlp.OTLPTracesEndpoint
      credentials: {
        managedIdentity: {
          resource: 'https://monitor.azure.com'
        }
      }
    }
    telemetry: {
      attributes: claimAttributes
    }
  }
}

output telemetryExporterId string = telemetryExporter.id
output telemetryExporterName string = telemetryExporter.name
@description('Grant this principal Monitoring Metrics Publisher on the data collection rule.')
output gatewayPrincipalId string = gateway.identity.principalId
output dataCollectionRuleId string = otlp.DataCollectionRuleResourceId
