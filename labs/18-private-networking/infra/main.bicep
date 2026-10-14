// Private networking for an existing AI Gateway.
// Creates the network pieces the gateway needs, without redeclaring the gateway itself:
//   - an NSG that allows outbound TCP 443 to the Storage and AzureKeyVault service tags
//   - a virtual network with an integration subnet (delegated to Microsoft.Web/serverFarms),
//     a private-endpoint subnet, and a small jumpbox subnet for testing
//   - optionally, an inbound private endpoint to the gateway (group ID "Gateway") registered in the
//     privatelink.azure-api.net private DNS zone
//   - optionally, a private endpoint to a Foundry resource (group ID "account") with its private DNS zones
// Outbound VNet integration and public network access are PATCH operations on the gateway. Run them with
// `az aigateway network update`, because a Bicep PUT on the gateway service would redeclare the whole resource.

@description('Name of the existing AI Gateway (API Management service with the AIGateway SKU).')
param gatewayName string

@description('Resource group of the existing AI Gateway. Defaults to the deployment resource group.')
param gatewayResourceGroup string = resourceGroup().name

@description('Region for the network resources. Use the gateway region: VNet integration requires the virtual network in the same region as the gateway.')
param location string = resourceGroup().location

@description('Name of the virtual network.')
param vnetName string = 'vnet-aigw'

@description('Address space of the virtual network.')
param vnetAddressPrefix string = '10.20.0.0/16'

@description('Name of the subnet dedicated to gateway VNet integration.')
param integrationSubnetName string = 'snet-aigw-integration'

@description('Prefix of the integration subnet. /27 is the minimum; /24 leaves room to scale.')
param integrationSubnetPrefix string = '10.20.0.0/24'

@description('Name of the subnet that holds private endpoints.')
param privateEndpointSubnetName string = 'snet-private-endpoints'

@description('Prefix of the private-endpoint subnet.')
param privateEndpointSubnetPrefix string = '10.20.1.0/24'

@description('Name of the subnet for the test VM (jumpbox).')
param jumpboxSubnetName string = 'snet-jumpbox'

@description('Prefix of the jumpbox subnet.')
param jumpboxSubnetPrefix string = '10.20.2.0/27'

@description('Name of the network security group attached to the integration subnet.')
param nsgName string = 'nsg-aigw-integration'

@description('Create the inbound private endpoint to the gateway. Deploy with false first, enable VNet integration, then redeploy with true.')
param includeGatewayPrivateEndpoint bool = false

@description('Name of the inbound private endpoint to the gateway.')
param gatewayPrivateEndpointName string = 'pe-${gatewayName}'

@description('Optional resource ID of a Foundry (AIServices) account to reach privately. Leave empty to skip.')
param foundryAccountId string = ''

@description('Name of the private endpoint to the Foundry account.')
param foundryPrivateEndpointName string = 'pe-foundry-${gatewayName}'

var includeFoundryPrivateEndpoint = !empty(foundryAccountId)

// Standard private DNS zones for Foundry (AIServices) accounts.
var foundryDnsZoneNames = [
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
]

resource gateway 'Microsoft.ApiManagement/service@2025-09-01-preview' existing = {
  name: gatewayName
  scope: resourceGroup(gatewayResourceGroup)
}

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowStorageOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Storage'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowKeyVaultOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureKeyVault'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

// Subnets are declared inline so that redeploying the template never tries to delete them.
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [ vnetAddressPrefix ]
    }
    subnets: [
      {
        name: integrationSubnetName
        properties: {
          addressPrefix: integrationSubnetPrefix
          networkSecurityGroup: {
            id: nsg.id
          }
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
      {
        name: privateEndpointSubnetName
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: jumpboxSubnetName
        properties: {
          addressPrefix: jumpboxSubnetPrefix
        }
      }
    ]
  }
}

resource integrationSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: vnet
  name: integrationSubnetName
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: vnet
  name: privateEndpointSubnetName
}

// Inbound: clients in the virtual network reach the gateway on a private IP.
resource gatewayDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (includeGatewayPrivateEndpoint) {
  name: 'privatelink.azure-api.net'
  location: 'global'
}

resource gatewayDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (includeGatewayPrivateEndpoint) {
  parent: gatewayDnsZone
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource gatewayPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (includeGatewayPrivateEndpoint) {
  name: gatewayPrivateEndpointName
  location: location
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'gateway'
        properties: {
          privateLinkServiceId: gateway.id
          groupIds: [ 'Gateway' ]
        }
      }
    ]
  }
}

resource gatewayPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (includeGatewayPrivateEndpoint) {
  parent: gatewayPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'apim-gateway'
        properties: {
          privateDnsZoneId: gatewayDnsZone.id
        }
      }
    ]
  }
}

// Outbound: the integrated gateway resolves the Foundry account to a private IP and calls it privately.
resource foundryDnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zoneName in foundryDnsZoneNames: if (includeFoundryPrivateEndpoint) {
  name: zoneName
  location: 'global'
}]

resource foundryDnsZoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zoneName, i) in foundryDnsZoneNames: if (includeFoundryPrivateEndpoint) {
  parent: foundryDnsZones[i]
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}]

resource foundryPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (includeFoundryPrivateEndpoint) {
  name: foundryPrivateEndpointName
  location: location
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'foundry'
        properties: {
          privateLinkServiceId: foundryAccountId
          groupIds: [ 'account' ]
        }
      }
    ]
  }
}

resource foundryPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (includeFoundryPrivateEndpoint) {
  parent: foundryPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [for (zoneName, i) in foundryDnsZoneNames: {
      name: replace(zoneName, '.', '-')
      properties: {
        privateDnsZoneId: foundryDnsZones[i].id
      }
    }]
  }
}

output vnetId string = vnet.id
output integrationSubnetId string = integrationSubnet.id
output privateEndpointSubnetId string = privateEndpointSubnet.id
output gatewayPrivateEndpointName string = includeGatewayPrivateEndpoint ? gatewayPrivateEndpoint.name : ''
output foundryPrivateEndpointName string = includeFoundryPrivateEndpoint ? foundryPrivateEndpoint.name : ''
