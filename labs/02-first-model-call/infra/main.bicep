// Publishes one Microsoft Foundry model deployment through an existing AI Gateway:
// grants the gateway's managed identity the Foundry User role on the account, creates a Foundry model
// provider that authenticates with that identity, registers the deployment as a backend model, publishes a
// callable alias for it, and creates a runtime API key for the first app.
// Mirrors the Foundry provider and model registration in infra/ai-gateway/main.bicep of the reference sample.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (API Management service with the AIGateway SKU) in this resource group.')
param gatewayName string

@description('Resource ID of the Foundry (Azure AI Services) or Azure OpenAI account. It can be in another resource group or subscription.')
param foundryAccountId string

@description('Name of the model deployment in that account, for example gpt-4.1-mini.')
param deploymentName string

@description('Version of the deployed model, for example 2025-04-14. Optional.')
param modelVersion string = ''

@description('Name of the model provider to create in the gateway.')
param providerName string = 'foundry-models'

@description('Callable alias that clients send in the request "model" field.')
param aliasName string = deploymentName

@description('Name of the runtime API key to create for the first app.')
param apiKeyName string = 'app-first-call'

@description('Tokens per minute that each caller identity can use on this model.')
@minValue(1)
param tokensPerMinute int = 10000

var foundryAccountName = last(split(foundryAccountId, '/'))
var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]
var deploymentId = '${foundryAccountId}/deployments/${deploymentName}'

resource aiGateway 'Microsoft.ApiManagement/service@2025-09-01-preview' existing = {
  name: gatewayName
}

resource defaultWorkspace 'Microsoft.ApiManagement/service/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  name: foundryAccountName
}

var foundryEndpoint = foundryAccount.properties.endpoint
var normalizedFoundryEndpoint = endsWith(foundryEndpoint, '/') ? foundryEndpoint : '${foundryEndpoint}/'

module foundryUserRole './foundry-user-role.bicep' = {
  name: take('foundry-user-${uniqueString(aiGateway.id, foundryAccountId)}', 64)
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    foundryAccountName: foundryAccountName
    gatewayPrincipalId: aiGateway.identity.principalId
    gatewayResourceId: aiGateway.id
  }
}

resource foundryProvider 'Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: providerName
  dependsOn: [
    foundryUserRole
  ]
  properties: {
    kind: 'Foundry'
    displayName: 'Foundry models'
    description: 'Managed-identity Foundry provider created by the first-model-call lab.'
    foundry: {
      endpoint: normalizedFoundryEndpoint
      resourceIds: [
        foundryAccountId
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: 'https://cognitiveservices.azure.com/'
        }
      }
    }
  }
}

resource model 'Microsoft.ApiManagement/service/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: foundryProvider
  name: deploymentName
  properties: {
    displayName: deploymentName
    description: 'Foundry deployment ${deploymentName} published through AI Gateway.'
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: deploymentId
      modelName: deploymentName
      modelVersion: empty(modelVersion) ? null : modelVersion
    }
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: tokensPerMinute
        counterKey: 'Identity'
      }
    ]
  }
}

resource alias 'Microsoft.ApiManagement/service/workspaces/aliases@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: aliasName
  properties: {
    backendModels: [
      { resourceId: model.id }
    ]
  }
}

resource runtimeApiKey 'Microsoft.ApiManagement/service/apiKeys@2025-09-01-preview' = {
  parent: aiGateway
  name: apiKeyName
  properties: {
    displayName: 'First call app key'
  }
}

output providerName string = foundryProvider.name
output modelName string = model.name
output aliasName string = alias.name
output apiKeyName string = runtimeApiKey.name
output gatewayUrl string = aiGateway.properties.gatewayUrl
output modelEndpoint string = '${aiGateway.properties.gatewayUrl}/default/models/openai/v1'
output foundryUserRoleAssignmentName string = foundryUserRole.outputs.roleAssignmentName
