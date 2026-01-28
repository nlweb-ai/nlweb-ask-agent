metadata description = 'Creates Azure AI Foundry Hub with AI Services connection'

@description('Name of the AI Foundry Hub')
param hubName string

@description('Name of the AI Services account')
param aiServicesName string

@description('Name of the Key Vault for AI Foundry workspace')
param keyVaultName string

@description('Location for resources')
param location string

@description('Tags for resources')
param tags object = {}

@description('Storage account resource ID')
param storageAccountId string

@description('Application Insights resource ID')
param applicationInsightsId string

@description('Container Registry resource ID (optional)')
param containerRegistryId string = ''

@description('Model deployments to create')
param deployments array = []

@description('SKU for AI Services')
param aiServicesSku string = 'S0'

// Key Vault for AI Foundry workspace (separate from app Key Vault to avoid circular deps)
resource aiFoundryKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// Azure AI Services (replaces standalone OpenAI)
resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aiServicesName
  location: location
  tags: tags
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: aiServicesName
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
  sku: {
    name: aiServicesSku
  }
}

// Model deployments under AI Services
@batchSize(1)
resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = [for deploy in deployments: {
  parent: aiServices
  name: deploy.name
  sku: {
    name: deploy.sku
    capacity: deploy.capacity
  }
  properties: {
    model: {
      format: deploy.?format ?? 'OpenAI'
      name: deploy.model
      version: deploy.version
    }
  }
}]

// AI Foundry Hub
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: hubName
  location: location
  tags: tags
  kind: 'Hub'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: hubName
    description: 'AI Foundry Hub for NLWeb'
    keyVault: aiFoundryKeyVault.id
    storageAccount: storageAccountId
    applicationInsights: applicationInsightsId
    containerRegistry: !empty(containerRegistryId) ? containerRegistryId : null
    publicNetworkAccess: 'Enabled'
    v1LegacyMode: false
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
}

// Connection from Hub to AI Services
resource aiServicesConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: aiHub
  name: 'aiservices-connection'
  properties: {
    category: 'AIServices'
    target: aiServices.properties.endpoint
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: aiServices.id
      Location: location
    }
  }
}

// Outputs
output hubId string = aiHub.id
output hubName string = aiHub.name
output hubPrincipalId string = aiHub.identity.principalId
output aiServicesId string = aiServices.id
output aiServicesName string = aiServices.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiServicesPrincipalId string = aiServices.identity.principalId
output aiServicesKey string = aiServices.listKeys().key1
