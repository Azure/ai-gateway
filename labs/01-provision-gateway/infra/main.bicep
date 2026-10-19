// Provisions an Azure AI Gateway (Microsoft.ApiManagement/aigateways) with a system-assigned managed
// identity, plus the companion connector gateway (Microsoft.Web/connectorGateways) with the same name.
// This matches what the AI Gateway portal creates: the connector gateway first, then the AI gateway.
targetScope = 'resourceGroup'

@description('Gateway name. It becomes the first label of the runtime host name, so use letters, numbers, and hyphens (max 24 characters).')
@minLength(1)
@maxLength(24)
param gatewayName string

@description('Region for the gateway. During public preview, Azure AI Gateway is available in East US 2 and Sweden Central.')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string = 'eastus2'

@description('Tags applied to both resources.')
param tags object = {}

@description('Optional subnet resource ID for outbound virtual network integration. It can only be set when the gateway is created.')
param backendSubnetId string = ''

resource connectorGateway 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  properties: {}
}

resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: union(
    {
      publicNetworkAccess: 'Enabled'
    },
    empty(backendSubnetId) ? {} : { backend: { subnet: { id: backendSubnetId } } }
  )
  dependsOn: [
    connectorGateway
  ]
}

output gatewayName string = aiGateway.name
output gatewayUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}'
output gatewayId string = aiGateway.id
output principalId string = aiGateway.identity.principalId
output connectorGatewayId string = connectorGateway.id
