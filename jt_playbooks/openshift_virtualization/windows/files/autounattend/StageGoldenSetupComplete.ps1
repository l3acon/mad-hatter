# Staged from the answer ISO during specialize: registers %SystemRoot%\Setup\Scripts\SetupComplete.cmd
# so GoldenBootstrap.ps1 runs before OOBE (avoids "computer restarted unexpectedly" loops on Server Core).
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$gb = Join-Path $here 'GoldenBootstrap.ps1'
if (-not (Test-Path -LiteralPath $gb)) {
    throw "GoldenBootstrap.ps1 not found on answer ISO beside this script: $gb"
}

$destDir = Join-Path $env:SystemRoot 'Setup\Scripts'
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item -LiteralPath $gb -Destination (Join-Path $destDir 'GoldenBootstrap.ps1') -Force

$cmdPath = Join-Path $destDir 'SetupComplete.cmd'
$lines = @(
    '@echo off',
    'set LOG=%SystemRoot%\Setup\Scripts\golden-bootstrap.log',
    'echo %date% %time% SetupComplete starting>>"%LOG%"',
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SystemRoot%\Setup\Scripts\GoldenBootstrap.ps1" 1>>"%LOG%" 2>>&1',
    'echo %date% %time% SetupComplete finished>>"%LOG%"'
)
$ascii = New-Object System.Text.ASCIIEncoding
[System.IO.File]::WriteAllText($cmdPath, ($lines -join "`r`n") + "`r`n", $ascii)
