metadata description = 'Creates Virtual Network with subnets for AKS and Application Load Balancer'

@description('Name of the virtual network')
param name string

@description('Location for resources')
param location string

@description('Tags to apply to resources')
param tags object = {}

@description('Address prefix for the virtual network')
param addressPrefix string = '10.0.0.0/16'

@description('Address prefix for AKS system node pool subnet')
param aksSystemSubnetPrefix string = '10.0.0.0/24'

@description('Address prefix for AKS user node pool subnet')
param aksUserSubnetPrefix string = '10.0.2.0/23'

@description('Address prefix for Application Load Balancer subnet')
param albSubnetPrefix string = '10.0.4.0/24'

// NSG for AKS subnets (minimal rules - AKS manages most)
// Note: ALB subnet delegated to Traffic Controller cannot have custom NSG rules - Azure manages it
resource aksNsg 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: 'nsg-aks-${name}'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// Virtual Network
resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        addressPrefix
      ]
    }
    subnets: [
      {
        name: 'snet-aks-system'
        properties: {
          addressPrefix: aksSystemSubnetPrefix
          networkSecurityGroup: {
            id: aksNsg.id
          }
        }
      }
      {
        name: 'snet-aks-user'
        properties: {
          addressPrefix: aksUserSubnetPrefix
          networkSecurityGroup: {
            id: aksNsg.id
          }
        }
      }
      {
        name: 'snet-alb'
        properties: {
          addressPrefix: albSubnetPrefix
          // No NSG - Azure manages security for Traffic Controller delegated subnets
          delegations: [
            {
              name: 'Microsoft.ServiceNetworking.trafficControllers'
              properties: {
                serviceName: 'Microsoft.ServiceNetworking/trafficControllers'
              }
            }
          ]
        }
      }
    ]
  }
}

// Outputs
output id string = vnet.id
output name string = vnet.name
output aksSystemSubnetId string = vnet.properties.subnets[0].id
output aksUserSubnetId string = vnet.properties.subnets[1].id
output albSubnetId string = vnet.properties.subnets[2].id
