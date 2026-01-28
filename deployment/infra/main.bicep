targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used to generate unique resource names')
param environmentName string

@description('Primary location for all resources. Must support gpt-4.1, gpt-4.1-mini, text-embedding-3-small, and phi-4 with GlobalStandard SKU.')
@metadata({
  azd: {
    type: 'location'
    usageName: [
      'OpenAI.GlobalStandard.gpt-4.1,30'
      'OpenAI.GlobalStandard.gpt-4.1-mini,30'
      'OpenAI.GlobalStandard.text-embedding-3-small,60'
      'OpenAI.GlobalStandard.phi-4,50'
    ]
  }
})
param location string

@description('Name of the resource group (generated if empty)')
param resourceGroupName string = ''

@description('Principal ID to grant access (typically your user ID for initial setup)')
param principalId string = ''

@description('Type of principal')
@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

@description('Application/Workload Identity principal ID (e.g., AKS managed identity)')
param appPrincipalId string = ''

@description('Location for Cosmos DB (defaults to main location if not specified)')
param cosmosLocation string = ''

@description('Location for SQL Server (defaults to main location if not specified)')
param sqlLocation string = ''

// Optional resource name overrides
param aiServicesName string = ''
param aiFoundryHubName string = ''
param appInsightsName string = ''
param searchServiceName string = ''
param cosmosAccountName string = ''
param sqlServerName string = ''
param storageAccountName string = ''
param keyVaultName string = ''
param acrName string = ''

// Model deployment capacities (in thousands of tokens per minute)
// Max quotas: gpt-4.1=5M, gpt-4.1-mini=150M, text-embedding-3-small=10M, phi-4=varies by region
param gpt4Capacity int = 1200
param gpt4MiniCapacity int = 50000
param embeddingCapacity int = 2000

// External PI Labs credentials (AzureML endpoint)
@description('PI Labs endpoint URL (external AzureML endpoint)')
@secure()
param piLabsEndpoint string

@description('PI Labs API key')
@secure()
param piLabsKey string

// AKS and Helm deployment parameters
@description('Hostname for the application (e.g., app.example.com)')
param hostname string = ''

@description('Email for Let\'s Encrypt certificate notifications')
param certManagerEmail string = ''

@description('Kubernetes version for AKS')
param kubernetesVersion string = '1.34'

@description('AKS system node pool VM size')
param aksSystemNodePoolVmSize string = 'Standard_D4s_v5'

@description('AKS user node pool VM size')
param aksUserNodePoolVmSize string = 'Standard_D4s_v5'

// Load abbreviations
var abbrs = loadJsonContent('./abbreviations.json')

// Generate unique resource token
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// Resource names
var rgName = !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
var aiServicesResolvedName = !empty(aiServicesName) ? aiServicesName : '${abbrs.cognitiveServicesAccounts}ai-${resourceToken}'
var aiFoundryHubResolvedName = !empty(aiFoundryHubName) ? aiFoundryHubName : '${abbrs.machineLearningServicesWorkspaces}hub-${resourceToken}'
var aiFoundryKvResolvedName = '${abbrs.keyVaultVaults}aif-${resourceToken}'
var appInsightsResolvedName = !empty(appInsightsName) ? appInsightsName : '${abbrs.insightsComponents}${resourceToken}'
var searchResolvedName = !empty(searchServiceName) ? searchServiceName : '${abbrs.searchSearchServices}${resourceToken}'
var cosmosResolvedName = !empty(cosmosAccountName) ? cosmosAccountName : '${abbrs.documentDBDatabaseAccounts}${resourceToken}'
var sqlResolvedName = !empty(sqlServerName) ? sqlServerName : '${abbrs.sqlServers}${resourceToken}'
var storageResolvedName = !empty(storageAccountName) ? storageAccountName : '${abbrs.storageStorageAccounts}${resourceToken}'
var kvResolvedName = !empty(keyVaultName) ? keyVaultName : '${abbrs.keyVaultVaults}${resourceToken}'
var acrResolvedName = !empty(acrName) ? acrName : '${abbrs.containerRegistryRegistries}${resourceToken}'

// AKS and networking resource names
var vnetResolvedName = '${abbrs.networkVirtualNetworks}${resourceToken}'
var aksResolvedName = '${abbrs.containerServiceManagedClusters}${resourceToken}'
var askApiIdentityName = '${abbrs.managedIdentityUserAssignedIdentities}askapi-${resourceToken}'
var crawlerIdentityName = '${abbrs.managedIdentityUserAssignedIdentities}crawler-${resourceToken}'
var kedaIdentityName = '${abbrs.managedIdentityUserAssignedIdentities}keda-${resourceToken}'
var deployIdentityName = '${abbrs.managedIdentityUserAssignedIdentities}deploy-${resourceToken}'
var albControllerIdentityName = '${abbrs.managedIdentityUserAssignedIdentities}alb-${resourceToken}'

// Tags
var tags = {
  'azd-env-name': environmentName
}

// Auto-generated SQL password (complex: uppercase + lowercase + number + special char)
var sqlAdminPassword = '${toUpper(uniqueString(subscription().id, resourceToken))}!${toLower(uniqueString(resourceToken, environmentName))}#1'

// Model deployments
var modelDeployments = [
  {
    name: 'gpt-4.1'
    model: 'gpt-4.1'
    version: '2025-04-14'
    sku: 'GlobalStandard'
    capacity: gpt4Capacity
  }
  {
    name: 'gpt-4.1-mini'
    model: 'gpt-4.1-mini'
    version: '2025-04-14'
    sku: 'GlobalStandard'
    capacity: gpt4MiniCapacity
  }
  {
    name: 'text-embedding-3-small'
    model: 'text-embedding-3-small'
    version: '1'
    sku: 'GlobalStandard'
    capacity: embeddingCapacity
  }
  {
    name: 'Phi-4'
    model: 'Phi-4'
    version: '7'
    format: 'Microsoft'
    sku: 'GlobalStandard'
    capacity: 1
  }
]

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: rgName
  location: location
  tags: tags
}

// Application Insights (required for AI Foundry)
module appInsights 'modules/application-insights.bicep' = {
  name: 'appInsights'
  scope: rg
  params: {
    name: appInsightsResolvedName
    location: location
    tags: tags
  }
}

// AI Foundry Hub with AI Services
module aiFoundry 'modules/ai-foundry.bicep' = {
  name: 'aiFoundry'
  scope: rg
  params: {
    hubName: aiFoundryHubResolvedName
    aiServicesName: aiServicesResolvedName
    keyVaultName: aiFoundryKvResolvedName
    location: location
    tags: tags
    storageAccountId: storage.outputs.id
    applicationInsightsId: appInsights.outputs.id
    containerRegistryId: acr.outputs.id
    deployments: modelDeployments
  }
}

// AI Search Service
module search 'modules/search.bicep' = {
  name: 'search'
  scope: rg
  params: {
    name: searchResolvedName
    location: location
    tags: tags
  }
}

// Cosmos DB (can be deployed to a different region if needed)
module cosmos 'modules/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    name: cosmosResolvedName
    location: !empty(cosmosLocation) ? cosmosLocation : location
    tags: tags
  }
}

// SQL Server (can be deployed to a different region if needed)
module sql 'modules/sql.bicep' = {
  name: 'sql'
  scope: rg
  params: {
    name: sqlResolvedName
    location: !empty(sqlLocation) ? sqlLocation : location
    tags: tags
    adminPassword: sqlAdminPassword
  }
}

// Storage Account
module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: storageResolvedName
    location: location
    tags: tags
  }
}

// Container Registry
module acr 'modules/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    name: acrResolvedName
    location: location
    tags: tags
  }
}

// Key Vault with secrets (no keys for Cosmos/Storage - using RBAC)
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  scope: rg
  params: {
    name: kvResolvedName
    location: location
    tags: tags
    principalId: principalId
    principalType: principalType
    secrets: {
      'AZURE-OPENAI-ENDPOINT': aiFoundry.outputs.aiServicesEndpoint
      'AZURE-OPENAI-KEY': aiFoundry.outputs.aiServicesKey
      'AZURE-SEARCH-ENDPOINT': search.outputs.endpoint
      'AZURE-SEARCH-KEY': search.outputs.adminKey
      'AZURE-SEARCH-INDEX-NAME': 'crawler-vectors'
      'COSMOS-DB-ENDPOINT': cosmos.outputs.endpoint
      'COSMOS-DB-DATABASE-NAME': cosmos.outputs.databaseName
      'COSMOS-DB-CONTAINER-NAME': cosmos.outputs.containerName
      'SQL-SERVER-FQDN': sql.outputs.fullyQualifiedDomainName
      'SQL-DATABASE': sql.outputs.databaseName
      'SQL-USERNAME': sql.outputs.adminLogin
      'SQL-PASSWORD': sqlAdminPassword
      'BLOB-STORAGE-ACCOUNT-NAME': storage.outputs.name
      'STORAGE-QUEUE-NAME': storage.outputs.queueName
      'STORAGE-BLOB-CONTAINER': storage.outputs.blobContainerName
      'ACR-LOGIN-SERVER': acr.outputs.loginServer
      'PI-LABS-ENDPOINT': piLabsEndpoint
      'PI-LABS-KEY': piLabsKey
    }
  }
}

// RBAC role assignments for the user principal (Cosmos DB and Storage use Azure AD auth)
module roles 'modules/roles.bicep' = if (!empty(principalId)) {
  name: 'roles'
  scope: rg
  params: {
    principalId: principalId
    principalType: principalType
    cosmosAccountId: cosmos.outputs.id
    storageAccountId: storage.outputs.id
    aiServicesAccountId: aiFoundry.outputs.aiServicesId
    aiFoundryHubId: aiFoundry.outputs.hubId
    searchServiceId: search.outputs.id
    acrId: acr.outputs.id
  }
}

// RBAC role assignments for the application identity (AKS workload identity, managed identity, etc.)
module appRoles 'modules/roles.bicep' = if (!empty(appPrincipalId)) {
  name: 'appRoles'
  scope: rg
  params: {
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
    cosmosAccountId: cosmos.outputs.id
    storageAccountId: storage.outputs.id
    aiServicesAccountId: aiFoundry.outputs.aiServicesId
    aiFoundryHubId: aiFoundry.outputs.hubId
    searchServiceId: search.outputs.id
    acrId: acr.outputs.id
  }
}

// ========== AKS Infrastructure ==========

// Virtual Network with subnets for AKS and ALB
module network 'modules/network.bicep' = {
  name: 'network'
  scope: rg
  params: {
    name: vnetResolvedName
    location: location
    tags: tags
  }
}

// AKS Cluster
module aks 'modules/aks.bicep' = {
  name: 'aks'
  scope: rg
  params: {
    name: aksResolvedName
    location: location
    tags: tags
    kubernetesVersion: kubernetesVersion
    systemNodePoolVmSize: aksSystemNodePoolVmSize
    userNodePoolVmSize: aksUserNodePoolVmSize
    aksSystemSubnetId: network.outputs.aksSystemSubnetId
    aksUserSubnetId: network.outputs.aksUserSubnetId
    acrId: acr.outputs.id
  }
}

// Workload Identities for AKS pods
module workloadIdentities 'modules/workload-identity.bicep' = {
  name: 'workloadIdentities'
  scope: rg
  params: {
    location: location
    tags: tags
    aksOidcIssuerUrl: aks.outputs.oidcIssuerUrl
    askApiIdentityName: askApiIdentityName
    crawlerIdentityName: crawlerIdentityName
    kedaIdentityName: kedaIdentityName
    deployIdentityName: deployIdentityName
    albControllerIdentityName: albControllerIdentityName
  }
}

// RBAC roles for workload identities
module workloadRoles 'modules/workload-roles.bicep' = {
  name: 'workloadRoles'
  scope: rg
  params: {
    askApiPrincipalId: workloadIdentities.outputs.askApiIdentityPrincipalId
    crawlerPrincipalId: workloadIdentities.outputs.crawlerIdentityPrincipalId
    kedaPrincipalId: workloadIdentities.outputs.kedaIdentityPrincipalId
    deployPrincipalId: workloadIdentities.outputs.deployIdentityPrincipalId
    albControllerPrincipalId: workloadIdentities.outputs.albControllerIdentityPrincipalId
    keyVaultId: keyVault.outputs.id
    storageAccountId: storage.outputs.id
    aksId: aks.outputs.id
    acrId: acr.outputs.id
    resourceGroupId: rg.id
    vnetId: network.outputs.id
    cosmosAccountId: cosmos.outputs.id
  }
}

// ALB Controller needs Reader role on the AKS node resource group (mc_*)
// This is required for the controller to discover and manage ALB resources
// Node RG name follows pattern: mc_<rg-name>_<aks-name>_<location> (lowercase)
var aksNodeResourceGroup = 'mc_${rgName}_${aksResolvedName}_${location}'

module albNodeRgRole 'modules/alb-node-rg-role.bicep' = {
  name: 'albNodeRgRole'
  scope: resourceGroup(aksNodeResourceGroup)
  params: {
    albControllerPrincipalId: workloadIdentities.outputs.albControllerIdentityPrincipalId
  }
}

// Helm values for post-provision script (output as JSON)
// Infrastructure charts (cert-manager, keda, alb-controller) are installed separately
var helmValuesObject = {
  global: {
    azure: {
      tenantId: tenant().tenantId
    }
    keyVault: {
      name: keyVault.outputs.name
      tenantId: tenant().tenantId
    }
    containerRegistry: {
      server: acr.outputs.loginServer
    }
    hostname: hostname
    tls: {
      enabled: !empty(hostname)
    }
    certManager: {
      email: certManagerEmail
    }
  }
  gateway: {
    enabled: true
    tls: {
      enabled: !empty(hostname)
    }
    alb: {
      subnetResourceId: network.outputs.albSubnetId
    }
  }
  'ask-api': {
    enabled: true
    serviceAccount: {
      name: 'ask-api-sa'
    }
    workloadIdentity: {
      clientId: workloadIdentities.outputs.askApiIdentityClientId
    }
  }
  crawler: {
    enabled: true
    serviceAccount: {
      name: 'crawler-sa'
    }
    workloadIdentity: {
      clientId: workloadIdentities.outputs.crawlerIdentityClientId
      kedaIdentityId: workloadIdentities.outputs.kedaIdentityClientId
    }
    autoscaling: {
      storageAccountName: storage.outputs.name
    }
  }
}

// Outputs for AZD
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_KEYVAULT_NAME string = keyVault.outputs.name
output AZURE_KEYVAULT_URI string = keyVault.outputs.uri
output AZURE_OPENAI_ENDPOINT string = aiFoundry.outputs.aiServicesEndpoint
output AZURE_OPENAI_NAME string = aiFoundry.outputs.aiServicesName
output AZURE_AI_FOUNDRY_HUB_NAME string = aiFoundry.outputs.hubName
output AZURE_APPLICATION_INSIGHTS_NAME string = appInsights.outputs.name
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_SEARCH_NAME string = search.outputs.name
output COSMOS_DB_ENDPOINT string = cosmos.outputs.endpoint
output COSMOS_DB_NAME string = cosmos.outputs.name
output SQL_SERVER string = sql.outputs.fullyQualifiedDomainName
output SQL_SERVER_NAME string = sql.outputs.name
output STORAGE_ACCOUNT_NAME string = storage.outputs.name
output ACR_LOGIN_SERVER string = acr.outputs.loginServer
output ACR_NAME string = acr.outputs.name

// AKS Outputs
output AKS_NAME string = aks.outputs.name
output AKS_OIDC_ISSUER_URL string = aks.outputs.oidcIssuerUrl
output VNET_NAME string = network.outputs.name
output ALB_SUBNET_ID string = network.outputs.albSubnetId
output ASK_API_IDENTITY_CLIENT_ID string = workloadIdentities.outputs.askApiIdentityClientId
output CRAWLER_IDENTITY_CLIENT_ID string = workloadIdentities.outputs.crawlerIdentityClientId
output KEDA_IDENTITY_CLIENT_ID string = workloadIdentities.outputs.kedaIdentityClientId
output ALB_CONTROLLER_IDENTITY_CLIENT_ID string = workloadIdentities.outputs.albControllerIdentityClientId
output HOSTNAME string = hostname

// Helm values JSON for post-provision script
output HELM_VALUES_JSON string = string(helmValuesObject)
