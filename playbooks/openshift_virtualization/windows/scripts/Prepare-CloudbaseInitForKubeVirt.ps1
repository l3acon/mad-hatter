#Requires -Version 5.1
<#
.SYNOPSIS
    Deprecated — forwards to prepare-win.ps1 (same directory).

.DESCRIPTION
    This file name is kept for existing bookmarks and docs. All preparation (Ansible WinRM bootstrap,
    firewall off, Cloudbase-Init, sysprep) lives in **prepare-win.ps1**.

.EXAMPLE
    .\Prepare-CloudbaseInitForKubeVirt.ps1 -Force -Verbose
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch] $Force,
    [string] $CloudbaseVersion = '1.1.8',
    [uri] $MsiDownloadUri = $null,
    [switch] $SkipSysprep,
    [ValidateSet('Auto', 'Oobe', 'NoOobe')]
    [string] $SysprepOobeMode = 'Auto'
)

$target = Join-Path $PSScriptRoot 'prepare-win.ps1'
if (-not (Test-Path -LiteralPath $target)) {
    throw "Expected prepare-win.ps1 next to this script: $target"
}
& $target @PSBoundParameters
