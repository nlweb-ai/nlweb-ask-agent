metadata description = 'Creates an Azure Kubernetes Service cluster with workload identity and required addons'

@description('Name of the AKS cluster')
param name string

@description('Location for resources')
param location string

@description('Tags to apply to resources')
param tags object = {}

@description('Kubernetes version')
param kubernetesVersion string = '1.34'

@description('VM size for system node pool')
param systemNodePoolVmSize string = 'Standard_D4s_v5'

@description('Node count for system node pool')
param systemNodePoolCount int = 2

@description('VM size for user node pool')
param userNodePoolVmSize string = 'Standard_D4s_v5'

@description('Minimum node count for user node pool')
param userNodePoolMinCount int = 2

@description('Maximum node count for user node pool')
param userNodePoolMaxCount int = 10

@description('Subnet ID for system node pool')
param aksSystemSubnetId string

@description('Subnet ID for user node pool')
param aksUserSubnetId string

@description('Container Registry ID for AcrPull role assignment')
param acrId string = ''

@description('Azure Monitor Workspace ID for Prometheus metrics collection (empty to disable)')
param monitorWorkspaceId string = ''

// AKS Cluster
resource aks 'Microsoft.ContainerService/managedClusters@2024-09-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    kubernetesVersion: kubernetesVersion
    dnsPrefix: name
    enableRBAC: true

    // CRITICAL: Enable OIDC for workload identity
    oidcIssuerProfile: {
      enabled: true
    }

    // Workload Identity
    securityProfile: {
      workloadIdentity: {
        enabled: true
      }
    }

    // Network Configuration - Azure CNI Overlay
    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      networkPolicy: 'azure'
      loadBalancerSku: 'standard'
      serviceCidr: '10.1.0.0/16'
      dnsServiceIP: '10.1.0.10'
    }

    // Node Pools
    agentPoolProfiles: [
      {
        name: 'system'
        mode: 'System'
        vmSize: systemNodePoolVmSize
        count: systemNodePoolCount
        vnetSubnetID: aksSystemSubnetId
        osType: 'Linux'
        osSKU: 'AzureLinux'
        enableAutoScaling: false
        maxPods: 110
      }
      {
        name: 'user'
        mode: 'User'
        vmSize: userNodePoolVmSize
        minCount: userNodePoolMinCount
        maxCount: userNodePoolMaxCount
        vnetSubnetID: aksUserSubnetId
        osType: 'Linux'
        osSKU: 'AzureLinux'
        enableAutoScaling: true
        maxPods: 110
      }
    ]

    // Addons
    addonProfiles: {
      // Azure Key Vault Secrets Provider (CSI Driver)
      azureKeyvaultSecretsProvider: {
        enabled: true
        config: {
          enableSecretRotation: 'true'
          rotationPollInterval: '5m'
        }
      }
    }

    // Azure Monitor - Prometheus metrics collection
    azureMonitorProfile: {
      metrics: {
        enabled: !empty(monitorWorkspaceId)
      }
    }

    // Auto-upgrade
    autoUpgradeProfile: {
      upgradeChannel: 'patch'
    }
  }
}

// Prometheus Data Collection Resources (only when monitor workspace is provided)
resource prometheusDataCollectionEndpoint 'Microsoft.Insights/dataCollectionEndpoints@2022-06-01' = if (!empty(monitorWorkspaceId)) {
  name: '${name}-prometheus-dce'
  location: location
  tags: tags
  properties: {
    networkAcls: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

resource prometheusDataCollectionRule 'Microsoft.Insights/dataCollectionRules@2022-06-01' = if (!empty(monitorWorkspaceId)) {
  name: '${name}-prometheus-dcr'
  location: location
  tags: tags
  properties: {
    dataCollectionEndpointId: prometheusDataCollectionEndpoint.id
    dataSources: {
      prometheusForwarder: [
        {
          name: 'PrometheusDataSource'
          streams: ['Microsoft-PrometheusMetrics']
          labelIncludeFilter: {}
        }
      ]
    }
    destinations: {
      monitoringAccounts: [
        {
          name: 'MonitoringAccount'
          accountResourceId: monitorWorkspaceId
        }
      ]
    }
    dataFlows: [
      {
        streams: ['Microsoft-PrometheusMetrics']
        destinations: ['MonitoringAccount']
      }
    ]
  }
}

resource prometheusRuleAssociation 'Microsoft.Insights/dataCollectionRuleAssociations@2022-06-01' = if (!empty(monitorWorkspaceId)) {
  name: '${name}-prometheus-dcra'
  scope: aks
  properties: {
    dataCollectionRuleId: prometheusDataCollectionRule.id
  }
}

// AcrPull role for kubelet identity
// Note: Using AKS name in GUID since kubelet objectId isn't known at deployment start
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(acrId)) {
  name: guid(acrId, name, 'acrpull', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: containerRegistry
  properties: {
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// Existing ACR reference for scoping
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = if (!empty(acrId)) {
  name: split(acrId, '/')[8]
}

// Outputs
output id string = aks.id
output name string = aks.name
output oidcIssuerUrl string = aks.properties.oidcIssuerProfile.issuerURL
output kubeletIdentityObjectId string = aks.properties.identityProfile.kubeletidentity.objectId
output principalId string = aks.identity.principalId
output nodeResourceGroup string = aks.properties.nodeResourceGroup
