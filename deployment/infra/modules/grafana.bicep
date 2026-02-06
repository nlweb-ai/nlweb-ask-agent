metadata description = 'Creates an Azure Managed Grafana instance with Prometheus data source'

@description('Name of the Grafana instance')
param name string

@description('Location for the resource')
param location string

@description('Tags for the resource')
param tags object = {}

@description('Azure Monitor Workspace ID to use as Prometheus data source')
param monitorWorkspaceId string

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

output id string = grafana.id
output name string = grafana.name
output principalId string = grafana.identity.principalId
output endpoint string = grafana.properties.endpoint
