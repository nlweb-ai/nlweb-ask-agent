metadata description = 'Creates Azure AI Search service'

@description('Name of the search service')
param name string

@description('Location for the resource')
param location string

@description('Tags for the resource')
param tags object = {}

@description('SKU name')
@allowed(['free', 'basic', 'standard', 'standard2', 'standard3'])
param sku string = 'standard'

@description('Semantic search tier')
@allowed(['disabled', 'free', 'standard'])
param semanticSearch string = 'free'

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hostingMode: 'default'
    partitionCount: 1
    replicaCount: 1
    publicNetworkAccess: 'enabled'
    semanticSearch: semanticSearch
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
  sku: {
    name: sku
  }
}

output id string = search.id
output name string = search.name
output endpoint string = 'https://${search.name}.search.windows.net'
output principalId string = search.identity.principalId
output adminKey string = search.listAdminKeys().primaryKey
