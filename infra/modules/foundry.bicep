param location string
param accountName string
param projectName string = 'proj-lgws'
param raiPolicyName string = 'lgws-strict'
param modelDeployments array

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: false
    dynamicThrottlingEnabled: false
    publicNetworkAccess: 'Enabled'
    restrictOutboundNetworkAccess: false
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
  }
}

@batchSize(1)
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [for deployment in modelDeployments: {
  parent: account
  name: deployment.name
  sku: {
    name: 'GlobalStandard'
    capacity: deployment.capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: deployment.modelName
      version: deployment.version
    }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: raiPolicyName
  }
  dependsOn: [
    raiPolicy
  ]
}]


var standardContentFilters = [
  {
    name: 'Hate'
    source: 'Prompt'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Hate'
    source: 'Completion'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Sexual'
    source: 'Prompt'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Sexual'
    source: 'Completion'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Violence'
    source: 'Prompt'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Violence'
    source: 'Completion'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Selfharm'
    source: 'Prompt'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Selfharm'
    source: 'Completion'
    severityThreshold: 'Low'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
]

var promptAttackFilters = [
  {
    name: 'Jailbreak'
    source: 'Prompt'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
  {
    name: 'Indirect Attack'
    source: 'Prompt'
    enabled: true
    blocking: true
    action: 'BLOCKING'
  }
]

resource raiPolicy 'Microsoft.CognitiveServices/accounts/raiPolicies@2025-06-01' = {
  parent: account
  name: raiPolicyName
  properties: {
    basePolicyName: 'Microsoft.DefaultV2'
    mode: 'Blocking'
    contentFilters: concat(standardContentFilters, promptAttackFilters)
  }
}

output accountResourceId string = account.id
output projectResourceId string = project.id
output projectPrincipalId string = project.identity.principalId
