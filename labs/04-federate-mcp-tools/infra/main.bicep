// Registers the public Microsoft Learn MCP server as a federated MCP server in an existing AI Gateway.
// Clients call one governed endpoint, https://<gateway>.eastus2-01.ai.gateway.azure.com/default/toolservers/<serverName>/mcp,
// and the gateway publishes each backend's tools with a namespace prefix (<namespace>_<tool>).
// Set secondNamespace to add the same public server as a second, optional backend and see namespacing at work.
// Set supportedVersions to pin the MCP protocol versions that clients can negotiate.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('MCP server name. It becomes part of the endpoint URL and cannot be changed after creation.')
param serverName string = 'learn'

@description('Display name shown in the portal catalog and details page.')
param displayName string = 'Microsoft Learn'

@description('Description that helps people and agents understand what the tools do.')
param serverDescription string = 'Search and fetch official Microsoft documentation and code samples.'

@description('Namespace for the first backend. Its tools are published as <namespace>_<tool>.')
param namespace string = 'learn'

@description('URL of the first backend MCP server (Streamable HTTP).')
param mcpUrl string = 'https://learn.microsoft.com/api/mcp'

@description('Optional namespace for a second backend. Leave empty to register one backend only.')
param secondNamespace string = ''

@description('URL of the optional second backend MCP server (Streamable HTTP).')
param secondMcpUrl string = 'https://learn.microsoft.com/api/mcp'

@description('Comma-separated MCP protocol versions the server supports, for example 2025-06-18 or 2026-07-28,2025-06-18. Every MCP backend must support every version you list. Leave empty to keep the legacy defaults: 2025-06-18, 2025-03-26, and 2024-11-05.')
param supportedVersions string = ''

var versions = empty(supportedVersions) ? {} : { versions: split(replace(supportedVersions, ' ', ''), ',') }

var primaryEndpoint = {
  namespace: namespace
  kind: 'mcp'
  mcp: {
    url: mcpUrl
    transport: 'streamableHttp'
  }
  required: true
}

var secondEndpoint = {
  namespace: secondNamespace
  kind: 'mcp'
  mcp: {
    url: secondMcpUrl
    transport: 'streamableHttp'
  }
  required: false
}

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

#disable-next-line BCP081
resource toolServer 'Microsoft.ApiManagement/aigateways/workspaces/toolServers@2025-09-01-preview' = {
  parent: workspace
  name: serverName
  properties: union({
    displayName: displayName
    description: serverDescription
    type: 'mcp'
    failureMode: 'failClosed'
    endpoints: empty(secondNamespace) ? [ primaryEndpoint ] : [ primaryEndpoint, secondEndpoint ]
  }, versions)
}

output toolServerId string = toolServer.id
output supportedVersions array = toolServer.properties.?versions ?? []
output mcpEndpoint string = 'https://${gateway.properties.frontend.defaultHostname}/default/toolservers/${serverName}/mcp'
