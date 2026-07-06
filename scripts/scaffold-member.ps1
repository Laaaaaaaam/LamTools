<#
.SYNOPSIS
  Scaffold a new LamTools member from core/templates/member.
.DESCRIPTION
  Usage:
    .\scripts\scaffold-member.ps1 -Id <MemberId> -Name <MemberName> [-DisplayName <DisplayName>] [-Capabilities <caps>] [-DryRun]
  Example:
    .\scripts\scaffold-member.ps1 -Id coder -Name LamCoder -DisplayName LamCoder -Capabilities code,git
    .\scripts\scaffold-member.ps1 -Id coder -Name LamCoder -DisplayName LamCoder -Capabilities code,git -DryRun
#>
param(
    [Parameter(Mandatory=$true)][string]$Id,
    [Parameter(Mandatory=$true)][string]$Name,
    [string]$DisplayName,
    [string[]]$Capabilities,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$TemplateDir = Join-Path $Root "core\templates\member"
$MemberId = $Id
$TargetDir = Join-Path $Root "members\$MemberId"
$PortsFile = Join-Path $Root "scripts\ports.json"

if (-not (Test-Path -LiteralPath $TemplateDir)) {
    Write-Host "Template directory not found: $TemplateDir" -ForegroundColor Red
    exit 1
}

if (Test-Path -LiteralPath $TargetDir) {
    Write-Host "Target directory already exists: $TargetDir" -ForegroundColor Red
    exit 1
}

$MemberName = $Name
$PascalName = $MemberId.Substring(0,1).ToUpper() + $MemberId.Substring(1)
$kebabName = $Name.ToLower()
$EnvPrefix = "LAM$($PascalName.ToUpper())"
if (-not $DisplayName) { $DisplayName = $Name }
if (-not $Capabilities) { $Capabilities = @() }

$Ports = Get-Content -LiteralPath $PortsFile -Raw | ConvertFrom-Json

$usedPorts = @()
foreach ($prop in $Ports.PSObject.Properties) {
    $entry = $prop.Value
    if ($entry.backend) { $usedPorts += $entry.backend }
    if ($entry.frontend_dev) { $usedPorts += $entry.frontend_dev }
}

$backendPort = 6170
while ($usedPorts -contains $backendPort) { $backendPort++ }
$frontendPort = $backendPort + 1
while ($usedPorts -contains $frontendPort) { $frontendPort++ }

$capabilityItems = @()
foreach ($capability in $Capabilities) {
    $capabilityItems += $capability -split ','
}

$capabilitiesJson = if ($capabilityItems.Count -gt 0) {
    $caps = $capabilityItems | ForEach-Object { $_.Trim() } | Where-Object { $_ } | ForEach-Object { "`"$_`"" }
    "[$($caps -join ',')]"
} else {
    "[]"
}

$replacements = @{
    '__MEMBER_ID__'       = $MemberId
    '__MEMBER_NAME__'     = $MemberName
    '__DISPLAY_NAME__'    = $DisplayName
    '__PASCAL_NAME__'     = $PascalName
    '__CAPABILITIES_JSON__' = $capabilitiesJson
    '__BACKEND_PORT__'    = [string]$backendPort
    '__FRONTEND_PORT__'   = [string]$frontendPort
    '__ENV_PREFIX__'      = $EnvPrefix
    '__KEBAB_NAME__'      = $kebabName
}

function Process-Content {
    param([string]$Content)
    if ([string]::IsNullOrEmpty($Content)) { return '' }
    foreach ($key in $replacements.Keys) {
        $Content = $Content.Replace($key, $replacements[$key])
    }
    return $Content
}

function Copy-TemplateDir {
    param([string]$Src, [string]$Dst)

    $items = Get-ChildItem -LiteralPath $Src -Recurse | Where-Object {
        $_.FullName -notmatch '\\__pycache__(\\|$)' -and $_.Extension -ne '.pyc'
    }
    foreach ($item in $items) {
        $relPath = $item.FullName.Substring($Src.Length)
        $targetPath = Join-Path $Dst $relPath

        if ($item.PSIsContainer) {
            if ($DryRun) {
                Write-Host "[DRY] mkdir $targetPath" -ForegroundColor Yellow
            } else {
                New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
            }
        } else {
            $content = Get-Content -LiteralPath $item.FullName -Raw -Encoding UTF8
            $processed = Process-Content $content

            if ($null -eq $processed -or $processed.Trim() -eq '') {
                $processed = ''
            }

            if ($DryRun) {
                $preview = if ($processed -and $processed.Length -gt 80) { $processed.Substring(0, 80) + '...' } else { $processed }
                Write-Host "[DRY] write $targetPath" -ForegroundColor Yellow
                Write-Host "      preview: $preview" -ForegroundColor DarkGray
            } else {
                    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
                    [System.IO.File]::WriteAllText($targetPath, $processed, $utf8NoBom)
                }
        }
    }
}

Write-Host ""
Write-Host "=== LamTools Member Scaffolder ===" -ForegroundColor Cyan
Write-Host "  Member ID:     $MemberId"
Write-Host "  Name:          $MemberName"
Write-Host "  DisplayName:   $DisplayName"
Write-Host "  Capabilities:  $($capabilityItems -join ',')"
Write-Host "  Env Prefix:    $EnvPrefix"
Write-Host "  Kebab Name:    $kebabName"
Write-Host "  Backend Port:  $backendPort"
Write-Host "  Frontend Port: $frontendPort"
Write-Host "  Target:        $TargetDir"
if ($DryRun) {
    Write-Host "  Mode:          DRY RUN (no files written)" -ForegroundColor Yellow
}
Write-Host ""

if (-not $DryRun) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

Copy-TemplateDir $TemplateDir $TargetDir

$ShimPath = Join-Path $Root "$MemberId.cmd"
$ShimContent = "@echo off`r`nchcp 65001 >nul 2>&1`r`npy -3.14 `"%~dp0scripts\member_cli.py`" $MemberId %*`r`n"

if ($DryRun) {
    Write-Host "[DRY] write $ShimPath" -ForegroundColor Yellow
    Write-Host "      preview: @echo off / chcp 65001 / py -3.14 member_cli.py $MemberId" -ForegroundColor DarkGray
} else {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($ShimPath, $ShimContent, $utf8NoBom)
    Write-Host "  CLI shim:     $ShimPath" -ForegroundColor Green
}

Write-Host ""
if ($DryRun) {
    Write-Host "Dry run complete. No files were written." -ForegroundColor Yellow
} else {
    Write-Host "Scaffold complete: $TargetDir" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. cd $TargetDir\backend && py -3.14 -m uvicorn app.main:app --reload --port $backendPort"
    Write-Host "  2. cd $TargetDir\frontend && npm run dev"
    Write-Host "  3. Fill backend/app/member/ prompts, tools, and verification policy"
    Write-Host "  4. Add business routers to backend/app/routers/ only for product APIs"
    Write-Host "  5. Fill WorkspaceShell slots with product-specific UI"
    Write-Host "  6. Update scripts/dev.ps1, build.ps1, test.ps1 to include $MemberId"
}
