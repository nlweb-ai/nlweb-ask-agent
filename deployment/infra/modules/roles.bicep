metadata description = 'Creates role assignments for a principal across Azure AI Foundry and other services'

@description('Principal ID to assign roles to')
param principalId string

@description('Type of principal')
@allowed(['User', 'ServicePrincipal', 'Group'])
param principalType string = 'User'

@description('Cosmos DB account ID for role assignment')
param cosmosAccountId string = ''

@description('Storage account ID for role assignment')
param storageAccountId string = ''

@description('AI Services account ID for role assignment')
param aiServicesAccountId string = ''

@description('AI Foundry Hub ID for role assignment')
param aiFoundryHubId string = ''

@description('Search service ID for role assignment')
param searchServiceId string = ''

@description('Container Registry ID for role assignment')
param acrId string = ''

// Role definition IDs
var roles = {
  // Cosmos DB
  cosmosDbDataContributor: '00000000-0000-0000-0000-000000000002' // Cosmos DB Built-in Data Contributor
  // Storage
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  // AI Services / OpenAI
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  // AI Foundry
  azureAiDeveloper: '64702f94-c441-49e6-a78b-ef80e0188fee'
  // Search
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  // Container Registry
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
}

// Cosmos DB Data Contributor
resource cosmosRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(cosmosAccountId) && !empty(principalId)) {
  name: '${split(cosmosAccountId, '/')[8]}/${guid(cosmosAccountId, principalId, roles.cosmosDbDataContributor)}'
  properties: {
    principalId: principalId
    roleDefinitionId: '${cosmosAccountId}/sqlRoleDefinitions/${roles.cosmosDbDataContributor}'
    scope: cosmosAccountId
  }
}

// Storage Blob Data Contributor
resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(storageAccountId) && !empty(principalId)) {
  name: guid(storageAccountId, principalId, roles.storageBlobDataContributor)
  scope: storageAccount
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
  }
}

// Storage Queue Data Contributor
resource storageQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(storageAccountId) && !empty(principalId)) {
  name: guid(storageAccountId, principalId, roles.storageQueueDataContributor)
  scope: storageAccount
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor)
  }
}

// Cognitive Services OpenAI User (on AI Services - backward compat for OpenAI models)
resource aiServicesOpenAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(aiServicesAccountId) && !empty(principalId)) {
  name: guid(aiServicesAccountId, principalId, roles.cognitiveServicesOpenAIUser)
  scope: aiServicesAccount
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser)
  }
}

// Cognitive Services User (broader access for non-OpenAI models)
resource aiServicesCognitiveRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(aiServicesAccountId) && !empty(principalId)) {
  name: guid(aiServicesAccountId, principalId, roles.cognitiveServicesUser)
  scope: aiServicesAccount
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
  }
}

// Azure AI Developer (on Hub - allows model deployment and management)
resource aiFoundryDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(aiFoundryHubId) && !empty(principalId)) {
  name: guid(aiFoundryHubId, principalId, roles.azureAiDeveloper)
  scope: aiFoundryHub
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAiDeveloper)
  }
}

// Search Index Data Contributor
resource searchIndexRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceId) && !empty(principalId)) {
  name: guid(searchServiceId, principalId, roles.searchIndexDataContributor)
  scope: searchService
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
  }
}

// Search Service Contributor
resource searchServiceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceId) && !empty(principalId)) {
  name: guid(searchServiceId, principalId, roles.searchServiceContributor)
  scope: searchService
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchServiceContributor)
  }
}

// ACR Pull
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(acrId) && !empty(principalId)) {
  name: guid(acrId, principalId, roles.acrPull)
  scope: containerRegistry
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

// Existing resource references for scoping
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (!empty(storageAccountId)) {
  name: split(storageAccountId, '/')[8]
}

resource aiServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = if (!empty(aiServicesAccountId)) {
  name: split(aiServicesAccountId, '/')[8]
}

resource aiFoundryHub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' existing = if (!empty(aiFoundryHubId)) {
  name: split(aiFoundryHubId, '/')[8]
}

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = if (!empty(searchServiceId)) {
  name: split(searchServiceId, '/')[8]
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = if (!empty(acrId)) {
  name: split(acrId, '/')[8]
}
