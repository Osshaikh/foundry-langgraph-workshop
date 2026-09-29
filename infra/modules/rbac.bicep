param principalId string
param principalType string
param accountName string
param projectName string
param searchServiceName string
param acrName string
param logAnalyticsName string
param appInsightsName string
param projectPrincipalId string
param searchPrincipalId string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: account
  name: projectName
}

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchServiceName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

var foundryUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
var foundryProjectManagerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'eadc314b-1a2d-4efa-be10-5d325db5065e')
var openAiContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a001fd3d-188f-4b5d-821b-7da978bf7442')
var searchServiceContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
var searchIndexDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
var acrPushRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8311e382-0749-4cb8-b61a-304f252e45ec')
var logAnalyticsReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '73c42c96-874c-492b-b04d-ab87d138a893')
var monitoringReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '43d0d8ad-25c7-4714-9337-8ba259a9fe05')
var searchIndexDataReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f')
var openAiUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')

resource attendeeFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, principalId, foundryUserRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: foundryUserRoleId
  }
}

resource attendeeProjectManager 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, principalId, foundryProjectManagerRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: foundryProjectManagerRoleId
  }
}

resource attendeeOpenAiContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, principalId, openAiContributorRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: openAiContributorRoleId
  }
}

var attendeeSearchRoles = [
  searchServiceContributorRoleId
  searchIndexDataContributorRoleId
]

resource attendeeSearchRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in attendeeSearchRoles: {
  scope: search
  name: guid(search.id, principalId, roleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: roleId
  }
}]

resource attendeeAcrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, principalId, acrPushRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: acrPushRoleId
  }
}

resource attendeeLogAnalyticsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: workspace
  name: guid(workspace.id, principalId, logAnalyticsReaderRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: logAnalyticsReaderRoleId
  }
}

resource attendeeMonitoringReaderOnWorkspace 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: workspace
  name: guid(workspace.id, principalId, monitoringReaderRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: monitoringReaderRoleId
  }
}

resource attendeeMonitoringReaderOnAppInsights 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: appInsights
  name: guid(appInsights.id, principalId, monitoringReaderRoleId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: monitoringReaderRoleId
  }
}

var projectSearchRoles = [
  searchIndexDataReaderRoleId
  searchServiceContributorRoleId
]

resource projectSearchRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in projectSearchRoles: {
  scope: search
  name: guid(search.id, projectPrincipalId, roleId)
  properties: {
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleId
  }
}]

resource searchOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, searchPrincipalId, openAiUserRoleId)
  properties: {
    principalId: searchPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: openAiUserRoleId
  }
}
