// Publishes gpt-6-astra through an existing AI Gateway so GitHub Copilot can use it as a bring-your-own-key model.
// Adds a gpt-6-astra deployment to the Foundry account the gateway already uses, then reuses the
// first-model-call lab's main.bicep to register the deployment, publish the gpt-6-astra alias with a
// per-caller token limit, and create the github-copilot runtime API key. The key value is never an output.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Resource ID of the Foundry (Azure AI Services) account that the gateway uses. It can be in another resource group.')
param foundryAccountId string

@description('Model to deploy and publish. The deployment and the alias both use this name.')
param modelName string = 'gpt-6-astra'

@description('Version of the model to deploy.')
param modelVersion string = '2026-09-03'

@description('Deployment SKU. Use DataZoneStandard if your GlobalStandard quota for the model is used up.')
@allowed([
  'GlobalStandard'
  'DataZoneStandard'
])
param skuName string = 'GlobalStandard'

@description('Deployment capacity in thousands of tokens per minute. Coding agents send large prompts, so give them room.')
@minValue(1)
param capacity int = 100

@description('Tokens per minute that each caller identity can use on the model through the gateway.')
@minValue(1000)
param tokensPerMinute int = 100000

@description('Name of the Foundry provider in the gateway. Use the name from lab 02 so the deployment registers under the same provider.')
param providerName string = 'foundry-models'

@description('Name of the runtime API key that GitHub Copilot uses.')
param apiKeyName string = 'github-copilot'

var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]

module deployment 'deployment.bicep' = {
  name: take('deploy-${modelName}', 64)
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    accountName: last(split(foundryAccountId, '/'))
    modelName: modelName
    modelVersion: modelVersion
    skuName: skuName
    capacity: capacity
  }
}

module publish '../../02-first-model-call/infra/main.bicep' = {
  name: take('publish-${modelName}', 64)
  params: {
    gatewayName: gatewayName
    foundryAccountId: foundryAccountId
    deploymentName: deployment.outputs.deploymentName
    modelVersion: modelVersion
    providerName: providerName
    aliasName: modelName
    apiKeyName: apiKeyName
    apiKeyDisplayName: 'GitHub Copilot'
    tokensPerMinute: tokensPerMinute
  }
}

output aliasName string = publish.outputs.aliasName
output apiKeyName string = publish.outputs.apiKeyName
output modelEndpoint string = publish.outputs.modelEndpoint
