// Publishes a rate-limited alias for an existing AI Gateway model.
// The alias points at the same backend model as your default alias, but carries its own token limit,
// so you can give a "batch" or "trial" audience a smaller allowance without touching the model.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
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

@description('Who gets a token counter: identity (each API key or Entra principal), ipAddress (each client IP address), or both.')
@allowed([ 'identity', 'ipAddress' ])
param counterKey array = [ 'identity' ]

resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' existing = {
  parent: workspace
  name: providerName
}

resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' existing = {
  parent: provider
  name: modelName
}

resource limitedAlias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
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
output chatCompletionsUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
