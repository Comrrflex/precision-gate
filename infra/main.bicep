targetScope = 'subscription'

@description('Azure region for the complete TCRIA -> Quinta Ordem -> Precision architecture.')
param location string

param resourceGroupName string

@minLength(5)
@maxLength(50)
param containerRegistryName string

param containerAppsEnvironmentName string = 'cae-precision-production'
param logAnalyticsWorkspaceName string = 'log-precision-production'
param tcriaAppName string = 'ca-tcria'
param quintaOrdemAppName string = 'ca-quinta-ordem'
param precisionAppName string = 'ca-precision-gate'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
}

module platform 'platform.bicep' = {
  name: 'precision-platform'
  scope: resourceGroup
  params: {
    location: location
    containerRegistryName: containerRegistryName
    containerAppsEnvironmentName: containerAppsEnvironmentName
    logAnalyticsWorkspaceName: logAnalyticsWorkspaceName
    tcriaAppName: tcriaAppName
    quintaOrdemAppName: quintaOrdemAppName
    precisionAppName: precisionAppName
  }
}

output resourceGroupName string = resourceGroup.name
output containerRegistryLoginServer string = platform.outputs.containerRegistryLoginServer
output tcriaUrl string = platform.outputs.tcriaUrl
output quintaOrdemUrl string = platform.outputs.quintaOrdemUrl
output precisionUrl string = platform.outputs.precisionUrl
