targetScope = 'subscription'

@description('Short lowercase attendee alias, 3-8 characters. Used in all lab resource names.')
@minLength(3)
@maxLength(8)
param alias string

@description('Azure region for all workshop resources.')
param location string = 'eastus2'

@description('Microsoft Entra object id of the signed-in workshop attendee.')
param principalId string

@description('Principal type for attendee role assignments.')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param principalType string = 'User'

@description('Capacity for the gpt-5.4-mini GlobalStandard deployment.')
param gpt54MiniCapacity int = 250

@description('Capacity for the gpt-5.4 GlobalStandard deployment.')
param gpt54Capacity int = 150

@description('Capacity for the text-embedding-3-large GlobalStandard deployment.')
param embeddingCapacity int = 150

@description('Capacity for the gpt-4.1-mini GlobalStandard deployment.')
param gpt41MiniCapacity int = 100

var normalizedAlias = toLower(alias)
var resourceGroupName = 'rg-lgws-${normalizedAlias}'
var foundryAccountName = 'aif-lgws-${normalizedAlias}'
var foundryProjectName = 'proj-lgws'
var searchServiceName = 'srch-lgws-${normalizedAlias}'
var logAnalyticsName = 'log-lgws-${normalizedAlias}'
var appInsightsName = 'appi-lgws-${normalizedAlias}'
var acrName = 'acrlgws${normalizedAlias}'
var raiPolicyName = 'lgws-strict'

resource labRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    workshop: 'foundry-langgraph'
    alias: normalizedAlias
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'lgws-monitoring-${normalizedAlias}'
  scope: labRg
  params: {
    location: location
    logAnalyticsName: logAnalyticsName
    appInsightsName: appInsightsName
  }
}

module search 'modules/search.bicep' = {
  name: 'lgws-search-${normalizedAlias}'
  scope: labRg
  params: {
    location: location
    searchServiceName: searchServiceName
  }
}

module acr 'modules/acr.bicep' = {
  name: 'lgws-acr-${normalizedAlias}'
  scope: labRg
  params: {
    location: location
    acrName: acrName
  }
}

module foundry 'modules/foundry.bicep' = {
  name: 'lgws-foundry-${normalizedAlias}'
  scope: labRg
  params: {
    location: location
    accountName: foundryAccountName
    projectName: foundryProjectName
    raiPolicyName: raiPolicyName
    modelDeployments: [
      {
        name: 'gpt-5.4-mini'
        modelName: 'gpt-5.4-mini'
        version: '2026-03-17'
        capacity: gpt54MiniCapacity
      }
      {
        name: 'gpt-5.4'
        modelName: 'gpt-5.4'
        version: '2026-03-05'
        capacity: gpt54Capacity
      }
      {
        name: 'text-embedding-3-large'
        modelName: 'text-embedding-3-large'
        version: '1'
        capacity: embeddingCapacity
      }
      {
        name: 'gpt-4.1-mini'
        modelName: 'gpt-4.1-mini'
        version: '2025-04-14'
        capacity: gpt41MiniCapacity
      }
    ]
  }
}

module connections 'modules/connections.bicep' = {
  name: 'lgws-connections-${normalizedAlias}'
  scope: labRg
  params: {
    accountName: foundryAccountName
    projectName: foundryProjectName
    searchServiceName: searchServiceName
    searchEndpoint: search.outputs.searchEndpoint
    appInsightsName: appInsightsName
    appInsightsResourceId: monitoring.outputs.appInsightsResourceId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    location: location
  }
}

module rbac 'modules/rbac.bicep' = {
  name: 'lgws-rbac-${normalizedAlias}'
  scope: labRg
  params: {
    principalId: principalId
    principalType: principalType
    accountName: foundryAccountName
    projectName: foundryProjectName
    searchServiceName: searchServiceName
    acrName: acrName
    logAnalyticsName: logAnalyticsName
    appInsightsName: appInsightsName
    projectPrincipalId: foundry.outputs.projectPrincipalId
    searchPrincipalId: search.outputs.searchPrincipalId
  }
}

output azureSubscriptionId string = subscription().subscriptionId
output azureResourceGroup string = resourceGroupName
output azureLocation string = location
output foundryAccountName string = foundryAccountName
output foundryProjectName string = foundryProjectName
output foundryProjectEndpoint string = 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
output foundryProjectResourceId string = foundry.outputs.projectResourceId
output azureAiModelDeploymentName string = 'gpt-5.4-mini'
output azureAiReasoningDeploymentName string = 'gpt-5.4'
output azureAiEmbeddingDeploymentName string = 'text-embedding-3-large'
output azureAiFinetuneBaseModel string = 'gpt-4.1-mini'
output azureSearchEndpoint string = search.outputs.searchEndpoint
output azureSearchConnectionName string = searchServiceName
output applicationInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString
output raiPolicyName string = raiPolicyName
output labPrefix string = 'lgws'
