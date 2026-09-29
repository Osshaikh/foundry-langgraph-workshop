#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]{3,8}$')]
    [string]$Alias,
    [string]$Location = 'eastus2'
)
$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$TemplateFile = Join-Path $RepoRoot 'infra\main.bicep'
$EnvFile = Join-Path $RepoRoot '.env'
function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "✓ $Message" -ForegroundColor Green }
function Require-Command([string]$Name) { if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Required command '$Name' was not found. Run scripts/install-tools.ps1 first." } }
function Invoke-AzDeployment([hashtable]$Capacities) {
    $deploymentName = "lgws-$Alias-$(Get-Date -Format yyyyMMddHHmmss)"
    $args = @('deployment','sub','create','--name',$deploymentName,'--location',$Location,'--template-file',$TemplateFile,'--parameters',"alias=$Alias","location=$Location","principalId=$PrincipalId",'principalType=User',"gpt54MiniCapacity=$($Capacities.gpt54MiniCapacity)","gpt54Capacity=$($Capacities.gpt54Capacity)","embeddingCapacity=$($Capacities.embeddingCapacity)","gpt41MiniCapacity=$($Capacities.gpt41MiniCapacity)",'-o','json')
    $output = & az @args 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
    return ($output | ConvertFrom-Json)
}
Write-Host 'Microsoft Foundry: LangGraph Hosted Agents Workshop provisioning' -ForegroundColor Green
Write-Host 'Estimated time: 10-15 minutes. This script creates fixed lab resources and writes .env.'
Require-Command az; Require-Command azd
Write-Step 'Checking Azure CLI sign-in'
try { $null = az account show -o none 2>$null } catch { az login -o none }
$SubscriptionId = az account show --query id -o tsv
$SubscriptionName = az account show --query name -o tsv
Write-Ok "Using subscription $SubscriptionName ($SubscriptionId)"
Write-Step 'Configuring Azure Developer CLI to reuse Azure CLI authentication'
azd config set auth.useAzCliAuth true | Out-Null
$exts = azd ext list 2>$null
if (($exts -join "`n") -notmatch 'azure\.ai\.agents') { azd ext install azure.ai.agents }
Write-Ok 'azd auth.useAzCliAuth=true and azure.ai.agents extension present'
Write-Step 'Registering Azure resource providers'
foreach ($provider in @('Microsoft.CognitiveServices','Microsoft.Search','Microsoft.ContainerRegistry','Microsoft.OperationalInsights','Microsoft.Insights')) {
    Write-Host "Registering $provider ..."; az provider register --namespace $provider --wait -o none
}
Write-Ok 'Resource providers registered'
Write-Step 'Reading signed-in user object id'
$PrincipalId = az ad signed-in-user show --query id -o tsv
if (-not $PrincipalId) { throw 'Could not read signed-in user object id.' }
Write-Ok "Principal id: $PrincipalId"
Write-Step 'Deploying workshop infrastructure'
try { $result = Invoke-AzDeployment -Capacities @{ gpt54MiniCapacity=250; gpt54Capacity=150; embeddingCapacity=150; gpt41MiniCapacity=100 } }
catch {
    if ($_.Exception.Message -match '(?i)quota|capacity|insufficient|limit') {
        Write-Host 'Quota/capacity error detected. Retrying once with half-size model capacities...' -ForegroundColor Yellow
        $result = Invoke-AzDeployment -Capacities @{ gpt54MiniCapacity=125; gpt54Capacity=75; embeddingCapacity=75; gpt41MiniCapacity=50 }
    } else { throw }
}
Write-Ok 'Azure resources deployed'
Write-Step 'Writing .env at the repository root'
$out = $result.properties.outputs
$envText = @"
AZURE_SUBSCRIPTION_ID=$($out.azureSubscriptionId.value)
AZURE_RESOURCE_GROUP=$($out.azureResourceGroup.value)
AZURE_LOCATION=$($out.azureLocation.value)
FOUNDRY_ACCOUNT_NAME=$($out.foundryAccountName.value)
FOUNDRY_PROJECT_NAME=$($out.foundryProjectName.value)
FOUNDRY_PROJECT_ENDPOINT=$($out.foundryProjectEndpoint.value)
FOUNDRY_PROJECT_RESOURCE_ID=$($out.foundryProjectResourceId.value)
AZURE_AI_MODEL_DEPLOYMENT_NAME=$($out.azureAiModelDeploymentName.value)
AZURE_AI_REASONING_DEPLOYMENT_NAME=$($out.azureAiReasoningDeploymentName.value)
AZURE_AI_EMBEDDING_DEPLOYMENT_NAME=$($out.azureAiEmbeddingDeploymentName.value)
AZURE_AI_FINETUNE_BASE_MODEL=$($out.azureAiFinetuneBaseModel.value)
AZURE_SEARCH_ENDPOINT=$($out.azureSearchEndpoint.value)
AZURE_SEARCH_CONNECTION_NAME=$($out.azureSearchConnectionName.value)
APPLICATIONINSIGHTS_CONNECTION_STRING=$($out.applicationInsightsConnectionString.value)
RAI_POLICY_NAME=$($out.raiPolicyName.value)
LAB_PREFIX=$($out.labPrefix.value)
"@
Set-Content -Path $EnvFile -Value $envText -Encoding utf8
Write-Ok "Wrote $EnvFile"
Write-Host "`nProvisioning complete" -ForegroundColor Green
Write-Host "Resource group: $($out.azureResourceGroup.value)"
Write-Host "Foundry project: $($out.foundryProjectEndpoint.value)"
Write-Host "Next: uv sync --extra docs, then open 00-preflight." -ForegroundColor Green
