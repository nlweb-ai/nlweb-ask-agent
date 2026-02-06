metadata description = 'Creates an Azure Managed Grafana instance with Prometheus data source'

@description('Name of the Grafana instance')
param name string

@description('Location for the resource')
param location string

@description('Tags for the resource')
param tags object = {}

@description('Azure Monitor Workspace ID to use as Prometheus data source')
param monitorWorkspaceId string

@description('Principal ID to grant Grafana Admin role (e.g. deploying user)')
param adminPrincipalId string = ''

@description('Principal type for the admin (User or ServicePrincipal)')
param adminPrincipalType string = 'User'

resource grafana 'Microsoft.Dashboard/grafana@2023-09-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    grafanaIntegrations: {
      azureMonitorWorkspaceIntegrations: [
        {
          azureMonitorWorkspaceResourceId: monitorWorkspaceId
        }
      ]
    }
    publicNetworkAccess: 'Enabled'
    zoneRedundancy: 'Disabled'
  }
}

// Monitoring Data Reader role for Grafana on Monitor Workspace
// This allows Grafana to query Prometheus metrics from the workspace
resource monitorWorkspaceRef 'Microsoft.Monitor/accounts@2023-04-03' existing = {
  name: split(monitorWorkspaceId, '/')[8]
}

resource grafanaMonitorDataReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(monitorWorkspaceId, grafana.id, 'monitoring-data-reader')
  scope: monitorWorkspaceRef
  properties: {
    principalId: grafana.identity.principalId
    principalType: 'ServicePrincipal'
    // Monitoring Data Reader role
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b0d8363b-8ddd-447d-831f-62ca05bff136')
  }
}

// Grafana Admin role for the deploying user
// This allows managing dashboards, data sources, etc. via the API
resource grafanaAdminRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adminPrincipalId)) {
  name: guid(grafana.id, adminPrincipalId, 'grafana-admin')
  scope: grafana
  properties: {
    principalId: adminPrincipalId
    principalType: adminPrincipalType
    // Grafana Admin role
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '22926164-76b3-42b3-bc55-97df8dab3e41')
  }
}

output id string = grafana.id
output name string = grafana.name
output principalId string = grafana.identity.principalId
output endpoint string = grafana.properties.endpoint
