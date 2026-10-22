// Quick start: everything for a first model call through Azure AI Gateway, in one deployment.
// Reuses the lab templates instead of repeating them:
//   1. ../../01-provision-gateway/infra/main.bicep  creates the gateway and its connector gateway.
//   2. ../../02-first-model-call/infra/foundry.bicep creates a Foundry account with one model deployment.
//   3. ../../02-first-model-call/infra/main.bicep    grants the gateway Foundry User on the account, adds the
//      Foundry provider, registers the model, publishes an alias, and creates a runtime API key.
// The names match lab 02, so you can continue with lab 03 on the same gateway.
targetScope = 'resourceGroup'

@description('Gateway name. It becomes the first label of the runtime host name (max 24 characters).')
@minLength(1)
@maxLength(24)
param gatewayName string = 'aigw-${uniqueString(resourceGroup().id)}'

@description('Name of the Foundry (Azure AI Services) account. It is also its globally unique subdomain.')
@minLength(2)
@maxLength(64)
param foundryAccountName string = 'aigw${uniqueString(resourceGroup().id)}'

@description('Region for the gateway and the Foundry account. During public preview, Azure AI Gateway is available in East US 2 and Sweden Central.')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string = 'eastus2'

@description('Model deployment to create in Foundry. Clients send this name, the alias, in the request "model" field.')
param deploymentName string = 'gpt-6-luna'

@description('Model version to deploy.')
param modelVersion string = '2026-09-22'

@description('Tags applied to the gateway and its connector gateway.')
param tags object = {}

module gateway '../../01-provision-gateway/infra/main.bicep' = {
  name: 'quickstart-gateway'
  params: {
    gatewayName: gatewayName
    location: location
    tags: tags
  }
}

module foundry '../../02-first-model-call/infra/foundry.bicep' = {
  name: 'quickstart-foundry'
  params: {
    accountName: foundryAccountName
    location: location
    deploymentName: deploymentName
    modelName: deploymentName
    modelVersion: modelVersion
  }
}

module publish '../../02-first-model-call/infra/main.bicep' = {
  name: 'quickstart-publish'
  params: {
    gatewayName: gateway.outputs.gatewayName
    foundryAccountId: foundry.outputs.accountId
    deploymentName: foundry.outputs.deploymentName
    modelVersion: modelVersion
  }
}

output gatewayName string = gateway.outputs.gatewayName
output gatewayId string = gateway.outputs.gatewayId
output gatewayUrl string = gateway.outputs.gatewayUrl
output modelEndpoint string = publish.outputs.modelEndpoint
output aliasName string = publish.outputs.aliasName
output apiKeyName string = publish.outputs.apiKeyName
output foundryAccountName string = foundry.outputs.accountName
