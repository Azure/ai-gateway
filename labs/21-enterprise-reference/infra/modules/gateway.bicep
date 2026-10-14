// The AI Gateway itself: an API Management service with the AIGateway SKU and a system-assigned managed identity,
// the connector gateway the sample deploys next to it, and the Foundry User role for the gateway identity on every
// Foundry account it calls. Mirrors infra/ai-gateway/main.bicep in the reference sample
// (Azure-Samples/simple-foundry-hosted-agent-python-aigateway).
targetScope = 'resourceGroup'

@description('Location of the gateway. The AI Gateway tier preview is available in East US 2 and Sweden Central.')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string

@description('Gateway name. It becomes the runtime host name, https://<name>.azure-api.net, so it must be globally unique.')
param gatewayName string

@description('Tags applied to the gateway.')
param tags object = {}

@description('Publisher email required by API Management.')
param publisherEmail string = 'noreply@example.com'

@description('Publisher name required by API Management.')
param publisherName string = 'AI Gateway'

@description('Resource IDs of the Foundry accounts the gateway calls with its managed identity.')
param foundryResourceIds array = []

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

resource connectorNamespace 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: gatewayName
  location: location
  properties: {}
  dependsOn: [
    aiGateway
  ]
}

module foundryUserRoleAssignments './foundry-user-role.bicep' = [for (foundryResourceId, i) in foundryResourceIds: {
  name: 'foundry-rbac-${i}-${uniqueString(foundryResourceId, gatewayName)}'
  scope: resourceGroup(split(foundryResourceId, '/')[2], split(foundryResourceId, '/')[4])
  params: {
    foundryAccountName: last(split(foundryResourceId, '/'))
    gatewayPrincipalId: aiGateway.identity.principalId
    gatewayResourceId: aiGateway.id
  }
}]

output gatewayName string = aiGateway.name
output gatewayId string = aiGateway.id
output gatewayUrl string = aiGateway.properties.gatewayUrl
output runtimeHostname string = replace(aiGateway.properties.gatewayUrl, 'https://', '')
output gatewayPrincipalId string = aiGateway.identity.principalId
output connectorNamespaceId string = connectorNamespace.id
output foundryUserRoleAssignmentNames array = [for (foundryResourceId, i) in foundryResourceIds: foundryUserRoleAssignments[i].outputs.roleAssignmentName]
