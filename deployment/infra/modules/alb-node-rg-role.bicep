metadata description = 'Assigns required roles to ALB controller on AKS node resource group'

targetScope = 'resourceGroup'

@description('Principal ID for ALB controller identity')
param albControllerPrincipalId string

// Role definition IDs
var roles = {
  reader: 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
  appGwForContainersConfigManager: 'fbc52c3f-28ad-4303-a892-8a056630b8f1'
}

// ALB Controller - Reader on AKS node resource group
resource albControllerReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, albControllerPrincipalId, roles.reader)
  properties: {
    principalId: albControllerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.reader)
  }
}

// ALB Controller - AppGw for Containers Configuration Manager on AKS node resource group
// Required for ALB controller to create/manage traffic controllers and frontends
resource albControllerConfigManagerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, albControllerPrincipalId, roles.appGwForContainersConfigManager)
  properties: {
    principalId: albControllerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.appGwForContainersConfigManager)
  }
}
