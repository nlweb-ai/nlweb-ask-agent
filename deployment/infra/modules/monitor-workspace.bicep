metadata description = 'Creates an Azure Monitor Workspace for Managed Prometheus metrics collection'

@description('Name of the Azure Monitor Workspace')
param name string

@description('Location for the resource')
param location string

@description('Tags for the resource')
param tags object = {}

resource monitorWorkspace 'Microsoft.Monitor/accounts@2023-04-03' = {
  name: name
  location: location
  tags: tags
}

output id string = monitorWorkspace.id
output name string = monitorWorkspace.name
