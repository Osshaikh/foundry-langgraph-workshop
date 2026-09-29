#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]{3,8}$')]
    [string]$Alias,
    [string]$Location = 'eastus2',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$rg = "rg-lgws-$Alias"
$account = "aif-lgws-$Alias"
if (-not $Force) {
    $confirm = Read-Host "Delete resource group '$rg' and purge Foundry account '$account'? Type DELETE to continue"
    if ($confirm -ne 'DELETE') { Write-Host 'Cancelled.'; exit 0 }
}
Write-Host "Starting resource group deletion: $rg" -ForegroundColor Yellow
az group delete -n $rg --yes --no-wait
Write-Host 'Waiting for resource group deletion before purge (this can take several minutes)...'
az group wait --name $rg --deleted
Write-Host "Purging soft-deleted Cognitive Services account: $account" -ForegroundColor Yellow
az cognitiveservices account purge --location $Location --resource-group $rg --name $account -o none
Write-Host 'Cleanup requested.' -ForegroundColor Green
