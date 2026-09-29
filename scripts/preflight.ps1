#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference = 'Continue'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$EnvPath = Join-Path $RepoRoot '.env'
$Results = New-Object System.Collections.Generic.List[object]
$RequiredFailures = 0
function Add-Result([string]$Check, [bool]$Pass, [string]$Fix, [bool]$Required = $true) { $script:Results.Add([pscustomobject]@{Check=$Check;Status=if($Pass){'PASS'}elseif($Required){'FAIL'}else{'WARN'};Fix=if($Pass){''}else{$Fix}}); if(-not $Pass -and $Required){$script:RequiredFailures++} }
function Cmd([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
function VersionString([string]$Command, [string[]]$Args) { try { (& $Command @Args 2>$null | Select-Object -First 1) -as [string] } catch { '' } }
function Test-MinVersion([string]$Version, [version]$Min) { try { ([version]([regex]::Match($Version, '\d+(\.\d+)+').Value)) -ge $Min } catch { $false } }
function Read-DotEnv([string]$Path) { $map=@{}; if(Test-Path $Path){ foreach($line in Get-Content $Path){ if($line -match '^\s*([^#=]+)=(.*)$'){ $map[$matches[1].Trim()]=$matches[2].Trim() } } }; return $map }
$pythonVersion = VersionString python @('--version')
Add-Result 'python >= 3.12' (Cmd python -and (Test-MinVersion $pythonVersion ([version]'3.12'))) 'Install Python 3.13 with scripts/install-tools.ps1.'
Add-Result 'uv installed' (Cmd uv) 'Install uv with scripts/install-tools.ps1.'
Add-Result 'git installed' (Cmd git) 'Install Git with scripts/install-tools.ps1.'
$azVersion = if (Cmd az) { az version --query '"azure-cli"' -o tsv 2>$null } else { '' }
Add-Result 'az >= 2.70' (Cmd az -and (Test-MinVersion $azVersion ([version]'2.70'))) 'Install/update Azure CLI.'
$azdVersion = VersionString azd @('version')
Add-Result 'azd >= 1.27.1' (Cmd azd -and (Test-MinVersion $azdVersion ([version]'1.27.1'))) 'Install/update Azure Developer CLI.'
$azdExt = if (Cmd azd) { (azd ext list 2>$null) -join "`n" } else { '' }
Add-Result 'azd ext azure.ai.agents' ($azdExt -match 'azure\.ai\.agents') 'Run: azd ext install azure.ai.agents.'
Add-Result 'az bicep available' ((Cmd az) -and ((az bicep version 2>$null) -match 'Bicep CLI')) 'Run: az bicep install.'
az account show -o none 2>$null; Add-Result 'az account show' ((Cmd az) -and ($LASTEXITCODE -eq 0)) 'Run: az login.'
azd auth login --check-status 2>$null; Add-Result 'azd auth login --check-status' ((Cmd azd) -and ($LASTEXITCODE -eq 0)) 'Run: azd config set auth.useAzCliAuth true, then azd auth login --check-status.'
$envMap = Read-DotEnv $EnvPath
$requiredKeys = @('AZURE_SUBSCRIPTION_ID','AZURE_RESOURCE_GROUP','AZURE_LOCATION','FOUNDRY_ACCOUNT_NAME','FOUNDRY_PROJECT_NAME','FOUNDRY_PROJECT_ENDPOINT','FOUNDRY_PROJECT_RESOURCE_ID','AZURE_AI_MODEL_DEPLOYMENT_NAME','AZURE_AI_REASONING_DEPLOYMENT_NAME','AZURE_AI_EMBEDDING_DEPLOYMENT_NAME','AZURE_AI_FINETUNE_BASE_MODEL','AZURE_SEARCH_ENDPOINT','AZURE_SEARCH_CONNECTION_NAME','APPLICATIONINSIGHTS_CONNECTION_STRING','RAI_POLICY_NAME','LAB_PREFIX')
$missing = @($requiredKeys | Where-Object { -not $envMap.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($envMap[$_]) })
Add-Result '.env required keys' ((Test-Path $EnvPath) -and $missing.Count -eq 0) "Run scripts/provision.ps1. Missing: $($missing -join ', ')"
if ($missing.Count -eq 0) {
    $deployments = az cognitiveservices account deployment list -g $envMap.AZURE_RESOURCE_GROUP -n $envMap.FOUNDRY_ACCOUNT_NAME --query '[].name' -o tsv 2>$null
    $needed = @($envMap.AZURE_AI_MODEL_DEPLOYMENT_NAME,$envMap.AZURE_AI_REASONING_DEPLOYMENT_NAME,$envMap.AZURE_AI_EMBEDDING_DEPLOYMENT_NAME,$envMap.AZURE_AI_FINETUNE_BASE_MODEL)
    $missingModels = @($needed | Where-Object { $deployments -notcontains $_ })
    Add-Result 'required model deployments exist' ($missingModels.Count -eq 0) "Re-run provision. Missing deployments: $($missingModels -join ', ')"
    $searchUrl = "$($envMap.AZURE_SEARCH_ENDPOINT)/indexes?api-version=2024-07-01"
    az rest --method get --url $searchUrl --resource https://search.azure.com -o none 2>$null
    Add-Result 'Azure AI Search reachable' ($LASTEXITCODE -eq 0) 'Wait for RBAC propagation or verify Search Index Data Contributor.'
    $me = az ad signed-in-user show --query id -o tsv 2>$null
    $roles = if ($me) { az role assignment list --assignee $me --scope $envMap.FOUNDRY_PROJECT_RESOURCE_ID --query '[].roleDefinitionName' -o tsv 2>$null } else { @() }
    Add-Result 'user roles on Foundry project' (($roles -join "`n") -match 'Foundry') 'Wait 5 minutes for role propagation.' $false
    Push-Location $RepoRoot
    try {
        $smoke = "from workshop.config import chat_model`nresp = chat_model().invoke('Reply with the single word pong.')`nprint(resp.content)"
        $smoke | uv run python - 2>$null | Out-Null
        Add-Result 'Foundry Responses smoke test' ($LASTEXITCODE -eq 0) 'Verify .env, role propagation, and model deployment health.'
    } finally { Pop-Location }
}
$Results | Format-Table -AutoSize
if ($RequiredFailures -gt 0) { exit 1 }
exit 0
