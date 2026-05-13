#Requires -Version 5.1
<#
.SYNOPSIS
    Install Cloudbase-Init, tune it for KubeVirt cloudInitNoCloud, then sysprep for golden-image capture.

.DESCRIPTION
    Intended to run once on a freshly installed Windows Server VM (Administrator session) before you
    seal the disk for OpenShift Virtualization / KubeVirt. After completion the VM shuts down; power off
    is normal — capture or clone the root DataVolume next.

    Typical use:
      1. Finish Windows setup and log in as Administrator.
      2. Download this script (replace BRANCH). You must use -Uri and -OutFile by name — a second
         positional argument causes "PositionalParameterNotFound" on Invoke-WebRequest:
           $u = 'https://raw.githubusercontent.com/l3acon/mad-hatter/BRANCH/playbooks/openshift_virtualization/windows/scripts/Prepare-CloudbaseInitForKubeVirt.ps1'
           [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
           Invoke-WebRequest -Uri $u -OutFile "$PWD\Prepare-CloudbaseInitForKubeVirt.ps1" -UseBasicParsing
         Alternative (works on older hosts):
           (New-Object System.Net.WebClient).DownloadFile($u, "$PWD\Prepare-CloudbaseInitForKubeVirt.ps1")
      3. From an elevated PowerShell (recommended):
           .\Prepare-CloudbaseInitForKubeVirt.ps1 -Force -Verbose
         From cmd.exe (avoid -Confirm:$false here — cmd can pass it as a string and break binding):
           powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Prepare-CloudbaseInitForKubeVirt.ps1 -Force -Verbose
         Or use -Command so PowerShell parses booleans:
           powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& .\Prepare-CloudbaseInitForKubeVirt.ps1 -Confirm:`$false -Verbose"

    -Force skips confirmation for MSI install and sysprep (non-interactive). -Confirm:$false works only when
    the outer shell is PowerShell, not cmd.exe.

.PARAMETER Force
    Run msiexec install and sysprep without prompting (use instead of -Confirm:$false when started from cmd.exe).

.PARAMETER CloudbaseVersion
    GitHub release tag to install (default 1.1.8).

.PARAMETER MsiDownloadUri
    Override MSI URL (default: GitHub release asset for CloudbaseInitSetup_<version>_x64.msi).

.PARAMETER SkipSysprep
    Install and configure only; do not run sysprep (for debugging).

.EXAMPLE
    .\Prepare-CloudbaseInitForKubeVirt.ps1 -Verbose

.EXAMPLE
    .\Prepare-CloudbaseInitForKubeVirt.ps1 -Force -Verbose

.EXAMPLE
    .\Prepare-CloudbaseInitForKubeVirt.ps1 -Confirm:$false -Verbose
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch] $Force,

    [string] $CloudbaseVersion = '1.1.8',

    [uri] $MsiDownloadUri = $null,

    [switch] $SkipSysprep
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    throw 'Run this script from an elevated PowerShell (Run as Administrator).'
}

# TLS for Invoke-WebRequest against GitHub
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$cbRoot = Join-Path $env:ProgramFiles 'Cloudbase Solutions\Cloudbase-Init'
$cbConfDir = Join-Path $cbRoot 'conf'
$msiName = "CloudbaseInitSetup_{0}_x64.msi" -f ($CloudbaseVersion -replace '\.', '_')
if (-not $MsiDownloadUri) {
    $MsiDownloadUri = "https://github.com/cloudbase/cloudbase-init/releases/download/$CloudbaseVersion/$msiName"
}

$msiLocal = Join-Path $env:TEMP $msiName

Write-Verbose "Downloading: $MsiDownloadUri"
Invoke-WebRequest -Uri $MsiDownloadUri -OutFile $msiLocal -UseBasicParsing

if ($Force -or $PSCmdlet.ShouldProcess($msiLocal, 'Install Cloudbase-Init (msiexec)')) {
    $p = Start-Process -FilePath msiexec.exe -ArgumentList @('/i', $msiLocal, '/qn', '/norestart') -Wait -PassThru
    if ($p.ExitCode -notin 0, 3010) {
        throw "msiexec failed with exit code $($p.ExitCode)"
    }
}

if (-not (Test-Path $cbConfDir)) {
    throw "Cloudbase-Init conf directory not found at '$cbConfDir'. Installation may have failed."
}

# Metadata: NoCloud / config-drive first (KubeVirt cloudInitNoCloud), then common clouds.
# Class names from cloudbase-init 1.1.x (see cloudbaseinit.metadata.services.*).
$nocloudFirst =
    'cloudbaseinit.metadata.services.nocloudservice.NoCloudConfigDriveService,' +
    'cloudbaseinit.metadata.services.configdrive.ConfigDriveService,' +
    'cloudbaseinit.metadata.services.ec2service.EC2Service,' +
    'cloudbaseinit.metadata.services.httpservice.HttpService,' +
    'cloudbaseinit.metadata.services.maasservice.MaaSHttpService'

function Update-CloudbaseConfFile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )
    if (-not (Test-Path $Path)) {
        Write-Warning "Skipping missing file: $Path"
        return
    }
    $stamp = Get-Date -Format 'yyyyMMddHHmmss'
    Copy-Item -Path $Path -Destination "$Path.bak.$stamp" -Force

    $text = Get-Content -LiteralPath $Path -Raw

    # Ensure config-drive / NoCloud media are scanned (ISO + CD paths).
    foreach ($pair in @(
            @{ Key = 'config_drive_cdrom'; Value = 'true' }
            @{ Key = 'config_drive_raw_hhd'; Value = 'true' }
        )) {
        if ($text -match "(?m)^\s*$([regex]::Escape($pair.Key))\s*=") {
            $text = $text -replace "(?m)^(\s*$([regex]::Escape($pair.Key))\s*=\s*).*$", "`$1$($pair.Value)"
        }
        else {
            if ($text -notmatch '\[DEFAULT\]') {
                $text = "[DEFAULT]`r`n" + $text
            }
            $text = $text -replace '(\[DEFAULT\]\s*\r?\n)', "`$1$($pair.Key)=$($pair.Value)`r`n"
        }
    }

    # Prepend NoCloud-related services to metadata_services= (once).
    if ($text -match 'nocloudservice\.NoCloudConfigDriveService') {
        Write-Verbose "metadata_services already references NoCloud (nocloudservice) in $Path"
    }
    elseif ($text -match '(?m)^(\s*metadata_services\s*=\s*)(.*)$') {
        $prefix = $Matches[1]
        $rest = $Matches[2].Trim()
        $newLine = "${prefix}$nocloudFirst$rest"
        $m = [regex]::Match($text, '(?m)^\s*metadata_services\s*=.*$')
        if (-not $m.Success) { throw "metadata_services regex mismatch in $Path" }
        $text = $text.Substring(0, $m.Index) + $newLine + $text.Substring($m.Index + $m.Length)
    }
    else {
        $inject = "`r`nmetadata_services=$nocloudFirst`r`n"
        if ($text -match '\[DEFAULT\]') {
            $text = $text -replace '(\[DEFAULT\]\s*\r?\n)', "`$1$inject"
        }
        else {
            $text = "[DEFAULT]$inject" + $text
        }
    }

    Set-Content -LiteralPath $Path -Value $text -Encoding utf8
    Write-Host "Updated $Path"
}

Update-CloudbaseConfFile -Path (Join-Path $cbConfDir 'cloudbase-init.conf')
Update-CloudbaseConfFile -Path (Join-Path $cbConfDir 'cloudbase-init-unattend.conf')

# Cloudbase ships Unattend.xml so sysprep runs the init pass with cloudbase-init-unattend.conf.
$unattendCandidates = @(
    (Join-Path $cbConfDir 'Unattend.xml')
    (Join-Path $cbRoot 'Unattend.xml')
)
$unattend = $unattendCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $unattend) {
    throw "Unattend.xml not found under '$cbConfDir'. Reinstall Cloudbase-Init or pass a custom unattend path."
}

Write-Host "Using unattend: $unattend"

# Ensure Cloudbase Init service starts after clone (installer usually sets Automatic).
Get-Service -Name 'cloudbase-init' -ErrorAction SilentlyContinue | Set-Service -StartupType Automatic -ErrorAction SilentlyContinue

if ($SkipSysprep) {
    Write-Warning 'SkipSysprep set: not running sysprep. Shut down manually when ready to capture the disk.'
    exit 0
}

$sysprep = Join-Path $env:SystemRoot 'System32\Sysprep\sysprep.exe'
if (-not (Test-Path -LiteralPath $sysprep)) {
    throw "Sysprep not found at $sysprep"
}

Write-Host 'Launching sysprep /generalize /oobe /shutdown (VM will power off when finished)...'
# Do not use Start-Process -ArgumentList with an array when /unattend includes spaces (Program Files).
# Sysprep then receives a truncated argv and prints only its USAGE banner.
$unattendArg = '/unattend:{0}' -f $unattend
Write-Host "Invoking: $sysprep /generalize /oobe /shutdown $unattendArg"

if ($Force -or $PSCmdlet.ShouldProcess($sysprep, "/generalize /oobe /shutdown $unattendArg")) {
    & $sysprep @('/generalize', '/oobe', '/shutdown', $unattendArg)
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "sysprep.exe exited with code $LASTEXITCODE"
    }
}
Write-Host 'Sysprep process exited (guest may still be shutting down).'
