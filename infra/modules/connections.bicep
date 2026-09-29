param accountName string
param projectName string
param searchServiceName string
param searchEndpoint string
param appInsightsName string
param appInsightsResourceId string
param appInsightsConnectionString string
param location string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: account
  name: projectName
}

resource searchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: searchServiceName
  properties: {
    category: 'CognitiveSearch'
    target: searchEndpoint
    authType: 'AAD'
    isSharedToAll: true
    useWorkspaceManagedIdentity: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: resourceId('Microsoft.Search/searchServices', searchServiceName)
      location: location
    }
  }
}

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: appInsightsName
  properties: {
    category: 'AppInsights'
    target: appInsightsResourceId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      #disable-next-line use-secure-value-for-secure-inputs
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsResourceId
      location: location
      ApplicationInsightsConnectionString: appInsightsConnectionString
    }
  }
}

output searchConnectionName string = searchConnection.name
output appInsightsConnectionName string = appInsightsConnection.name
