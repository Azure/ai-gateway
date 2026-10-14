// Provisions an Azure AI Gateway: an API Management service with the AIGateway SKU and a system-assigned
// managed identity, plus the companion connector gateway resource with the same name.
// Mirrors infra/ai-gateway/main.bicep in the reference sample
// (https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway).
targetScope = 'resourceGroup'

@description('Globally unique gateway name. It becomes part of the runtime URL, so use letters, numbers, and hyphens.')
@minLength(1)
@maxLength(50)
param gatewayName string

@description('Region for the gateway. During public preview, use eastus2 (East US 2) or swedencentral (Sweden Central).')
param location string = resourceGroup().location

@description('Tags applied to the gateway.')
param tags object = {}

@description('Publisher email required by the underlying API Management service.')
param publisherEmail string = 'noreply@example.com'

@description('Publisher name required by the underlying API Management service.')
param publisherName string = 'AI Gateway'

resource aiGateway 'Microsoft.ApiManagement/service@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'AIGateway'
    capacity: 1
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource connectorGateway 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: gatewayName
  location: location
  properties: {}
  dependsOn: [
    aiGateway
  ]
}

output gatewayName string = aiGateway.name
output gatewayUrl string = aiGateway.properties.gatewayUrl
output gatewayId string = aiGateway.id
output principalId string = aiGateway.identity.principalId
output connectorGatewayId string = connectorGateway.id
