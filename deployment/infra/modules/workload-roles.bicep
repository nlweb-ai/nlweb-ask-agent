metadata description = 'Creates RBAC role assignments for AKS workload identities'

@description('Principal ID for Ask API identity')
param askApiPrincipalId string

@description('Principal ID for Crawler identity')
param crawlerPrincipalId string

@description('Principal ID for KEDA identity')
param kedaPrincipalId string

@description('Principal ID for deployment script identity')
param deployPrincipalId string

@description('Principal ID for ALB controller identity')
param albControllerPrincipalId string

@description('Key Vault resource ID')
param keyVaultId string

@description('Storage account resource ID')
param storageAccountId string

@description('AKS cluster resource ID')
param aksId string

@description('Container Registry resource ID')
param acrId string

@description('Resource Group ID for Contributor role')
param resourceGroupId string

@description('Virtual Network ID for Network Contributor role')
param vnetId string

@description('Cosmos DB account ID for role assignment')
param cosmosAccountId string

// Role definition IDs
// Note: Cosmos DB uses its own RBAC system with different role IDs
var cosmosRoles = {
  dataContributor: '00000000-0000-0000-0000-000000000002' // Cosmos DB Built-in Data Contributor
}

// Azure RBAC role definition IDs
var roles = {
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageQueueDataReader: '19e7f393-937e-4f77-808e-94535e297925'
  storageQueueDataMessageProcessor: '8a0f0c08-91a1-4084-bc3d-661d67233fed'
  aksClusterAdmin: '0ab0b1a8-8aac-4efd-b8c2-3ee1fb270be8'
  acrPush: '8311e382-0749-4cb8-b61a-304f252e45ec'
  contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
  appGwForContainersConfigManager: 'fbc52c3f-28ad-4303-a892-8a056630b8f1'
  networkContributor: '4d97b98b-1d4f-4787-a291-c67834d212e7'
}

// Existing resource references
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: split(keyVaultId, '/')[8]
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: split(storageAccountId, '/')[8]
}

resource aks 'Microsoft.ContainerService/managedClusters@2024-09-01' existing = {
  name: split(aksId, '/')[8]
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: split(acrId, '/')[8]
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' existing = {
  name: split(vnetId, '/')[8]
}

// ========== Ask API Roles ==========

// Ask API - Key Vault Secrets User
resource askApiKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultId, askApiPrincipalId, roles.keyVaultSecretsUser)
  scope: keyVault
  properties: {
    principalId: askApiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
  }
}

// Ask API - Cosmos DB Data Contributor
resource askApiCosmosRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: '${split(cosmosAccountId, '/')[8]}/${guid(cosmosAccountId, askApiPrincipalId, cosmosRoles.dataContributor)}'
  properties: {
    principalId: askApiPrincipalId
    roleDefinitionId: '${cosmosAccountId}/sqlRoleDefinitions/${cosmosRoles.dataContributor}'
    scope: cosmosAccountId
  }
}

// ========== Crawler Roles ==========

// Crawler - Key Vault Secrets User
resource crawlerKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultId, crawlerPrincipalId, roles.keyVaultSecretsUser)
  scope: keyVault
  properties: {
    principalId: crawlerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
  }
}

// Crawler - Cosmos DB Data Contributor
resource crawlerCosmosRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: '${split(cosmosAccountId, '/')[8]}/${guid(cosmosAccountId, crawlerPrincipalId, cosmosRoles.dataContributor)}'
  properties: {
    principalId: crawlerPrincipalId
    roleDefinitionId: '${cosmosAccountId}/sqlRoleDefinitions/${cosmosRoles.dataContributor}'
    scope: cosmosAccountId
  }
}

// Crawler - Storage Blob Data Contributor
resource crawlerBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, crawlerPrincipalId, roles.storageBlobDataContributor)
  scope: storageAccount
  properties: {
    principalId: crawlerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
  }
}

// Crawler - Storage Queue Data Contributor
resource crawlerQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, crawlerPrincipalId, roles.storageQueueDataContributor)
  scope: storageAccount
  properties: {
    principalId: crawlerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor)
  }
}

// ========== KEDA Roles ==========

// KEDA - Storage Queue Data Reader (required to read queue length for scaling decisions)
resource kedaQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, kedaPrincipalId, roles.storageQueueDataReader)
  scope: storageAccount
  properties: {
    principalId: kedaPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataReader)
  }
}

// ========== Deployment Script Roles ==========

// Deploy - AKS Cluster Admin
resource deployAksRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aksId, deployPrincipalId, roles.aksClusterAdmin)
  scope: aks
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.aksClusterAdmin)
  }
}

// Deploy - AcrPush
resource deployAcrRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrId, deployPrincipalId, roles.acrPush)
  scope: acr
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPush)
  }
}

// Deploy - Contributor on Resource Group (for ALB addon enablement)
resource deployContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroupId, deployPrincipalId, roles.contributor)
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.contributor)
  }
}

// ========== ALB Controller Roles ==========

// ALB Controller - AppGw for Containers Configuration Manager on Resource Group
resource albControllerConfigManagerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroupId, albControllerPrincipalId, roles.appGwForContainersConfigManager)
  properties: {
    principalId: albControllerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.appGwForContainersConfigManager)
  }
}

// ALB Controller - Network Contributor on VNet (required to join ALB subnet)
resource albControllerNetworkRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vnetId, albControllerPrincipalId, roles.networkContributor)
  scope: vnet
  properties: {
    principalId: albControllerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.networkContributor)
  }
}
