#requires -Version 5.1
[CmdletBinding()]
param([switch]$CheckOnly, [switch]$IncludeDocker, [switch]$IncludeNode)
$ErrorActionPreference = 'Continue'
function Refresh-Path { $env:Path = "{0};{1}" -f [Environment]::GetEnvironmentVariable('Path','Machine'), [Environment]::GetEnvironmentVariable('Path','User') }
function Has-Command([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
function Test-Python313 {
    if (Has-Command py) { try { py -3.13 --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { return $true } } catch {} }
    if (Has-Command python) { try { return ((python --version 2>$null) -match 'Python 3\.13') } catch {} }
    return $false
}
function Install-Winget([string]$Id, [string]$Name) { if ($CheckOnly) { return }; if (-not (Has-Command winget)) { Write-Warning 'winget not found. Install App Installer.'; return }; winget install --id $Id --exact --accept-package-agreements --accept-source-agreements --silent; Refresh-Path }
function Version-Of([string]$Command, [string[]]$Args) { if (-not (Has-Command $Command)) { return 'missing' }; try { return ((& $Command @Args 2>$null | Select-Object -First 1) -as [string]) } catch { return 'installed' } }
function Ensure-CodeExtension([string]$Id) { if (-not (Has-Command code)) { return }; $installed = code --list-extensions 2>$null; if ($installed -notcontains $Id -and -not $CheckOnly) { code --install-extension $Id --force | Out-Null } }
Refresh-Path
$tools = @(@{Name='Git';Command='git';Winget='Git.Git'},@{Name='Python 3.13';Command='python';Winget='Python.Python.3.13'},@{Name='uv';Command='uv';Winget='astral-sh.uv'},@{Name='Azure CLI';Command='az';Winget='Microsoft.AzureCLI'},@{Name='Azure Developer CLI';Command='azd';Winget='Microsoft.Azd'},@{Name='PowerShell 7';Command='pwsh';Winget='Microsoft.PowerShell'},@{Name='VS Code';Command='code';Winget='Microsoft.VisualStudioCode'})
if ($IncludeDocker) { $tools += @{Name='Docker Desktop';Command='docker';Winget='Docker.DockerDesktop'} }
if ($IncludeNode) { $tools += @{Name='Node.js LTS';Command='node';Winget='OpenJS.NodeJS.LTS'} }
foreach ($tool in $tools) { $present = if ($tool.Name -eq 'Python 3.13') { Test-Python313 } else { Has-Command $tool.Command }; if ($present) { Write-Host "OK $($tool.Name) already installed" -ForegroundColor Green } else { Write-Host "MISSING $($tool.Name)" -ForegroundColor Yellow; Install-Winget $tool.Winget $tool.Name } }
Refresh-Path
if (Has-Command azd -and -not $CheckOnly) { azd config set auth.useAzCliAuth true | Out-Null; $exts = azd ext list 2>$null; if (($exts -join "`n") -notmatch 'azure\.ai\.agents') { azd ext install azure.ai.agents } }
if (Has-Command code -and -not $CheckOnly) { @('ms-python.python','ms-toolsai.jupyter','ms-windows-ai-studio.windows-ai-studio','ms-azuretools.vscode-bicep','ms-azuretools.vscode-docker') | ForEach-Object { Ensure-CodeExtension $_ } }
function Value-OrMissing([scriptblock]$Script, [string]$Missing = 'missing') {
    try { if (& $Script) { return (& $Script) } } catch {}
    return $Missing
}
$versionRows = @(
    [pscustomobject]@{Tool='Git'; Version=$(if (Has-Command git) { git --version } else { 'missing' })}
    [pscustomobject]@{Tool='Python'; Version=$(if (Has-Command py) { py -3.13 --version 2>$null } elseif (Has-Command python) { python --version } else { 'missing' })}
    [pscustomobject]@{Tool='uv'; Version=$(if (Has-Command uv) { uv --version } else { 'missing' })}
    [pscustomobject]@{Tool='Azure CLI'; Version=$(if (Has-Command az) { if ($CheckOnly) { 'installed' } else { az --version | Select-Object -First 1 } } else { 'missing' })}
    [pscustomobject]@{Tool='azd'; Version=$(if (Has-Command azd) { if ($CheckOnly) { 'installed' } else { azd version | Select-Object -First 1 } } else { 'missing' })}
    [pscustomobject]@{Tool='azd azure.ai.agents'; Version=$(if ($CheckOnly) { 'check in preflight' } elseif (Has-Command azd) { $exts = azd ext list 2>$null; if (($exts -join '`n') -match 'azure\.ai\.agents') { 'installed' } else { 'missing' } } else { 'missing' })}
    [pscustomobject]@{Tool='PowerShell'; Version=$(if (Has-Command pwsh) { pwsh -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()' } else { 'missing' })}
    [pscustomobject]@{Tool='VS Code'; Version=$(if (Has-Command code) { if ($CheckOnly) { 'installed' } else { code --version | Select-Object -First 1 } } else { 'missing' })}
    [pscustomobject]@{Tool='Docker'; Version=$(if (Has-Command docker) { docker --version } else { 'optional-missing' })}
    [pscustomobject]@{Tool='Node'; Version=$(if (Has-Command node) { node --version } else { 'optional-missing' })}
)
$versionRows | Format-Table -AutoSize
Write-Host 'If a newly installed command is still missing, restart your terminal.' -ForegroundColor Yellow
