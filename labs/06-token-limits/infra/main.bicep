// Publishes a rate-limited alias for an existing AI Gateway model.
// The alias points at the same backend model as your default alias, but carries its own token limit,
// so you can give a "batch" or "trial" audience a smaller allowance without touching the model.

@description('Name of the existing AI Gateway (API Management service with the AIGateway SKU).')
param gatewayName string

@description('Name of the existing model provider in the gateway, for example foundry-models.')
param providerName string

@description('Name of the existing backend model registration under the provider.')
param modelName string

@description('Callable alias to create. Clients send this value in the request "model" field.')
param aliasName string = '${modelName}-limited'

@description('Tokens allowed per period for each caller.')
@minValue(1)
param allowedTokens int = 1000

@description('Token limit window.')
@allowed([ 'minute', 'hour', 'day' ])
param period string = 'minute'

@description('Count tokens per caller identity (API key or Entra principal) or per client IP address.')
@allowed([ 'Identity', 'IPAddress' ])
param counterKey string = 'Identity'

resource gateway 'Microsoft.ApiManagement/service@2025-09-01-preview' existing = {
  name: gatewayName
}

resource workspace 'Microsoft.ApiManagement/service/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

resource provider 'Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview' existing = {
  parent: workspace
  name: providerName
}

resource model 'Microsoft.ApiManagement/service/workspaces/modelProviders/models@2025-09-01-preview' existing = {
  parent: provider
  name: modelName
}

resource limitedAlias 'Microsoft.ApiManagement/service/workspaces/aliases@2025-09-01-preview' = {
  parent: workspace
  name: aliasName
  properties: {
    backendModels: [
      { resourceId: model.id }
    ]
    policies: [
      {
        type: 'tokenLimit'
        count: allowedTokens
        period: period
        counterKey: counterKey
      }
    ]
  }
}

output aliasName string = limitedAlias.name
output chatCompletionsUrl string = 'https://${gatewayName}.azure-api.net/default/models/openai/v1/chat/completions'
