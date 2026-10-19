locals {
  private_dns_zones = var.enable_private_networking ? {
    gateway           = "privatelink.azure-api.net"
    cognitiveservices = "privatelink.cognitiveservices.azure.com"
    openai            = "privatelink.openai.azure.com"
    services          = "privatelink.services.ai.azure.com"
  } : {}
  private_subnets = var.enable_private_networking ? {
    gateway   = cidrsubnet(var.private_network_address_prefix, 8, 0)
    endpoints = cidrsubnet(var.private_network_address_prefix, 8, 1)
    client    = cidrsubnet(var.private_network_address_prefix, 8, 2)
  } : {}
  private_endpoints = var.enable_private_networking ? {
    gateway = {
      resource_id = azapi_resource.gateway.id
      group_id    = "Gateway"
      dns_keys    = ["gateway"]
    }
    models = {
      resource_id = azapi_resource.models.id
      group_id    = "account"
      dns_keys    = ["cognitiveservices", "openai", "services"]
    }
  } : {}
}

resource "azapi_resource" "private_vnet" {
  count     = var.enable_private_networking ? 1 : 0
  type      = "Microsoft.Network/virtualNetworks@2024-05-01"
  name      = "${local.names.gateway}-vnet"
  parent_id = azapi_resource.resource_group["gateway"].id
  location  = var.gateway_location
  tags      = local.tags
  body = {
    properties = { addressSpace = { addressPrefixes = [var.private_network_address_prefix] } }
  }
}

resource "azapi_resource" "private_nsg" {
  for_each  = var.enable_private_networking ? toset(["gateway", "client"]) : toset([])
  type      = "Microsoft.Network/networkSecurityGroups@2024-05-01"
  name      = "${local.names.gateway}-${each.key}-nsg"
  parent_id = azapi_resource.resource_group["gateway"].id
  location  = var.gateway_location
  tags      = local.tags
  body = {
    properties = {
      securityRules = each.key == "client" ? [{
        name = "DenyAllInbound"
        properties = {
          priority                 = 100
          direction                = "Inbound"
          access                   = "Deny"
          protocol                 = "*"
          sourcePortRange          = "*"
          destinationPortRange     = "*"
          sourceAddressPrefix      = "*"
          destinationAddressPrefix = "*"
        }
        }] : [for index, service in ["Storage", "AzureKeyVault"] : {
        name = "Allow${service}Https"
        properties = {
          priority                 = 100 + index
          direction                = "Outbound"
          access                   = "Allow"
          protocol                 = "Tcp"
          sourcePortRange          = "*"
          destinationPortRange     = "443"
          sourceAddressPrefix      = "VirtualNetwork"
          destinationAddressPrefix = service
        }
      }]
    }
  }
}

resource "azapi_resource" "private_subnet" {
  for_each  = local.private_subnets
  type      = "Microsoft.Network/virtualNetworks/subnets@2024-05-01"
  name      = each.key
  parent_id = azapi_resource.private_vnet[0].id
  locks     = [azapi_resource.private_vnet[0].id]
  body = {
    properties = merge(
      { addressPrefix = each.value },
      each.key == "endpoints" ? { privateEndpointNetworkPolicies = "Disabled" } : {},
      each.key != "endpoints" ? {
        networkSecurityGroup = { id = azapi_resource.private_nsg[each.key].id }
      } : {},
      each.key == "gateway" ? {
        delegations = [{
          name       = "gateway-integration"
          properties = { serviceName = "Microsoft.Web/serverFarms" }
        }]
      } : {},
      # Only the isolated PoC client uses default outbound internet for its VM agent.
      each.key == "client" ? { defaultOutboundAccess = true } : {}
    )
  }
}

resource "azapi_resource" "private_dns_zone" {
  for_each  = local.private_dns_zones
  type      = "Microsoft.Network/privateDnsZones@2020-06-01"
  name      = each.value
  parent_id = azapi_resource.resource_group["gateway"].id
  location  = "global"
  tags      = local.tags
  body      = { properties = {} }
}

resource "azapi_resource" "private_dns_link" {
  for_each  = local.private_dns_zones
  type      = "Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01"
  name      = "gateway-vnet"
  parent_id = azapi_resource.private_dns_zone[each.key].id
  location  = "global"
  body = {
    properties = {
      registrationEnabled = false
      virtualNetwork      = { id = azapi_resource.private_vnet[0].id }
    }
  }
}

resource "azapi_resource" "private_endpoint" {
  for_each  = local.private_endpoints
  type      = "Microsoft.Network/privateEndpoints@2024-05-01"
  name      = "${local.names.gateway}-${each.key}-pe"
  parent_id = azapi_resource.resource_group["gateway"].id
  location  = var.gateway_location
  tags      = local.tags
  body = {
    properties = {
      subnet = { id = azapi_resource.private_subnet["endpoints"].id }
      privateLinkServiceConnections = [{
        name = each.key
        properties = {
          privateLinkServiceId = each.value.resource_id
          groupIds             = [each.value.group_id]
        }
      }]
    }
  }
}

resource "azapi_resource" "private_dns_zone_group" {
  for_each  = local.private_endpoints
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01"
  name      = "default"
  parent_id = azapi_resource.private_endpoint[each.key].id
  body = {
    properties = {
      privateDnsZoneConfigs = [for key in each.value.dns_keys : {
        name       = key
        properties = { privateDnsZoneId = azapi_resource.private_dns_zone[key].id }
      }]
    }
  }
}
