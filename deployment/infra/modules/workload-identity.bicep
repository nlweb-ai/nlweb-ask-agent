metadata description = 'Creates user-assigned managed identities with federated credentials for AKS workload identity'

@description('Location for resources')
param location string

@description('Tags to apply to resources')
param tags object = {}

@description('AKS OIDC issuer URL for federation')
param aksOidcIssuerUrl string

@description('Name for the Ask API identity')
param askApiIdentityName string

@description('Name for the Crawler identity')
param crawlerIdentityName string

@description('Name for the KEDA identity')
param kedaIdentityName string

@description('Name for the deployment script identity')
param deployIdentityName string

@description('Name for the ALB controller identity')
param albControllerIdentityName string

// Ask API Managed Identity
resource askApiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: askApiIdentityName
  location: location
  tags: tags
}

// Ask API Federated Credential
resource askApiFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: askApiIdentity
  name: 'ask-api-federation'
  properties: {
    issuer: aksOidcIssuerUrl
    subject: 'system:serviceaccount:ask-api:ask-api-sa'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

// Crawler Managed Identity
resource crawlerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: crawlerIdentityName
  location: location
  tags: tags
}

// Crawler Federated Credential
resource crawlerFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: crawlerIdentity
  name: 'crawler-federation'
  properties: {
    issuer: aksOidcIssuerUrl
    subject: 'system:serviceaccount:crawler:crawler-sa'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

// KEDA Managed Identity
resource kedaIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: kedaIdentityName
  location: location
  tags: tags
}

// KEDA Federated Credential
resource kedaFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: kedaIdentity
  name: 'keda-federation'
  properties: {
    issuer: aksOidcIssuerUrl
    subject: 'system:serviceaccount:keda:keda-operator'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

// Deployment Script Managed Identity (for running Helm deployments)
resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: deployIdentityName
  location: location
  tags: tags
}

// ALB Controller Managed Identity
resource albControllerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: albControllerIdentityName
  location: location
  tags: tags
}

// ALB Controller Federated Credential
// IMPORTANT: The federated credential MUST be named 'azure-alb-identity' per Azure documentation
// See: https://learn.microsoft.com/en-us/azure/application-gateway/for-containers/quickstart-deploy-application-gateway-for-containers-alb-controller
resource albControllerFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: albControllerIdentity
  name: 'azure-alb-identity'
  properties: {
    issuer: aksOidcIssuerUrl
    subject: 'system:serviceaccount:azure-alb-system:alb-controller-sa'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

// Outputs
output askApiIdentityId string = askApiIdentity.id
output askApiIdentityClientId string = askApiIdentity.properties.clientId
output askApiIdentityPrincipalId string = askApiIdentity.properties.principalId

output crawlerIdentityId string = crawlerIdentity.id
output crawlerIdentityClientId string = crawlerIdentity.properties.clientId
output crawlerIdentityPrincipalId string = crawlerIdentity.properties.principalId

output kedaIdentityId string = kedaIdentity.id
output kedaIdentityClientId string = kedaIdentity.properties.clientId
output kedaIdentityPrincipalId string = kedaIdentity.properties.principalId

output deployIdentityId string = deployIdentity.id
output deployIdentityClientId string = deployIdentity.properties.clientId
output deployIdentityPrincipalId string = deployIdentity.properties.principalId

output albControllerIdentityId string = albControllerIdentity.id
output albControllerIdentityClientId string = albControllerIdentity.properties.clientId
output albControllerIdentityPrincipalId string = albControllerIdentity.properties.principalId
