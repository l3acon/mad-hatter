#Requires -Version 5.1
<#
.SYNOPSIS
    Configure WinRM for Ansible, disable Windows Firewall, install Cloudbase-Init for KubeVirt, then sysprep for golden-image capture.

.DESCRIPTION
    Intended to run once on a freshly installed Windows Server VM (Administrator session) before you
    seal the disk for OpenShift Virtualization / KubeVirt. Order of operations:

      1. Download and run Ansible's **ConfigureRemotingForAnsible.ps1** (enables PS Remoting / WinRM,
         LocalAccountTokenFilterPolicy, HTTP/HTTPS listeners, optional CredSSP). Use **-WinRmSkipNetworkProfileCheck**
         (default: on) so guests on the **Public** network profile still configure (typical lab / KubeVirt).
      2. **Disable the Windows Firewall** on all profiles so automation execution environments can reach
         **5985/5986** without host-based blocks (cluster NetworkPolicy may still apply).
      3. Install Cloudbase-Init, patch **cloudbase-init.conf** for NoCloud/config-drive, then **sysprep**.

    After completion the VM shuts down; power off is normal — capture or clone the root DataVolume next.
    On Windows Server Core, sysprep omits **/oobe** by default (OOBE wizard is not available there).

    Typical use:
      1. Finish Windows setup and log in as Administrator (install VirtIO / NetKVM first if needed).
      2. Download this script (replace BRANCH). Use **-Uri** and **-OutFile** by name:
           $u = 'https://raw.githubusercontent.com/l3acon/mad-hatter/BRANCH/playbooks/openshift_virtualization/windows/scripts/prepare-win.ps1'
           [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
           Invoke-WebRequest -Uri $u -OutFile "$PWD\prepare-win.ps1" -UseBasicParsing
      3. From an elevated PowerShell:
           .\prepare-win.ps1 -Force -Verbose
         From cmd.exe:
           powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\prepare-win.ps1 -Force -Verbose

    **ConfigureRemotingForAnsible.ps1** is intended for lab/eval (self-signed certs). Production should use
    CA-signed certificates and stricter auth. See: https://docs.ansible.com/ansible/latest/os_guide/windows_winrm.html

.PARAMETER Force
    Run remoting script acceptance, MSI install, and sysprep without prompting (use from cmd.exe instead of -Confirm:$false).

.PARAMETER SkipWinRmConfiguration
    Skip downloading/running ConfigureRemotingForAnsible.ps1 (not recommended for AAP / Ansible).

.PARAMETER SkipFirewallDisable
    Skip disabling Windows Firewall (leave default firewall rules only).

.PARAMETER AnsibleConfigureRemotingUri
    URL to download **ConfigureRemotingForAnsible.ps1** (default: ansible-documentation devel branch).

.PARAMETER ConfigureRemotingScriptPath
    If set, use this local script path instead of downloading from **AnsibleConfigureRemotingUri**.

.PARAMETER WinRmSkipNetworkProfileCheck
    Passed to ConfigureRemotingForAnsible.ps1 as **-SkipNetworkProfileCheck**. Default **true** for KubeVirt/lab NICs (Public profile).

.PARAMETER WinRmCertValidityDays
    Passed through as **-CertValidityDays** (default 1095).

.PARAMETER WinRmForceNewSSLCert
    Passed through as **-ForceNewSSLCert** (e.g. after a previous sysprep changed machine identity).

.PARAMETER WinRmGlobalHttpFirewallAccess
    Passed through as **-GlobalHttpFirewallAccess** (Ansible script widens WinRM HTTP firewall rule).

.PARAMETER WinRmEnableCredSSP
    Passed through as **-EnableCredSSP**.

.PARAMETER CloudbaseVersion
    GitHub release tag to install (default 1.1.8).

.PARAMETER MsiDownloadUri
    Override MSI URL (default: GitHub release asset for CloudbaseInitSetup_<version>_x64.msi).

.PARAMETER SkipSysprep
    Install and configure only; do not run sysprep (for debugging).

.PARAMETER SysprepOobeMode
    **Auto** (default): omit /oobe on **Windows Server Core**; use /oobe on other SKUs. **Oobe** / **NoOobe** override.

.PARAMETER AllowSystemContext
    Allow **NT AUTHORITY\SYSTEM** (for example **SetupComplete.cmd** during unattended install). Default requires Administrator.

.EXAMPLE
    .\prepare-win.ps1 -Verbose

.EXAMPLE
    .\prepare-win.ps1 -Force -Verbose

.EXAMPLE
    .\prepare-win.ps1 -ConfigureRemotingScriptPath D:\offline\ConfigureRemotingForAnsible.ps1 -Force -Verbose
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch] $Force,

    [switch] $SkipWinRmConfiguration,

    [switch] $SkipFirewallDisable,

    [uri] $AnsibleConfigureRemotingUri = 'https://raw.githubusercontent.com/ansible/ansible-documentation/refs/heads/devel/examples/scripts/ConfigureRemotingForAnsible.ps1',

    [string] $ConfigureRemotingScriptPath = '',

    [bool] $WinRmSkipNetworkProfileCheck = $true,

    [int] $WinRmCertValidityDays = 1095,

    [switch] $WinRmForceNewSSLCert,

    [switch] $WinRmGlobalHttpFirewallAccess,

    [switch] $WinRmEnableCredSSP,

    [string] $CloudbaseVersion = '1.1.8',

    [uri] $MsiDownloadUri = $null,

    [switch] $SkipSysprep,

    [ValidateSet('Auto', 'Oobe', 'NoOobe')]
    [string] $SysprepOobeMode = 'Auto',

    [switch] $AllowSystemContext
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-WindowsServerCoreInstallation {
    try {
        $it = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' `
                -Name InstallationType -ErrorAction Stop).InstallationType
        return ($null -ne $it) -and ($it -eq 'Server Core')
    }
    catch {
        return $false
    }
}

function Test-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Disable-WindowsFirewallAllProfiles {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [switch] $Force
    )
    $caption = 'Disable Windows Firewall (all profiles: Domain, Private, Public)'
    if (-not ($Force -or $PSCmdlet.ShouldProcess($env:COMPUTERNAME, $caption))) {
        Write-Warning 'Skipping firewall disable (no -Force and confirmation declined).'
        return
    }
    Write-Verbose 'Disabling Windows Firewall on all profiles so WinRM and other automation ports are not blocked locally.'
    try {
        if (Get-Command Set-NetFirewallProfile -ErrorAction SilentlyContinue) {
            Set-NetFirewallProfile -Profile Domain, Private, Public -Enabled False -ErrorAction Stop
        }
        else {
            throw 'Set-NetFirewallProfile not available'
        }
    }
    catch {
        Write-Verbose "Set-NetFirewallProfile failed ($($_.Exception.Message)); using netsh advfirewall fallback."
        $p = Start-Process -FilePath netsh.exe -ArgumentList @('advfirewall', 'set', 'allprofiles', 'state', 'off') -Wait -PassThru -NoNewWindow
        if ($p.ExitCode -ne 0) {
            throw "netsh advfirewall set allprofiles state off failed with exit code $($p.ExitCode)"
        }
    }
    Write-Host 'Windows Firewall has been turned OFF for all profiles.'
}

function Invoke-AnsibleConfigureRemotingScript {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $LocalScriptPath,

        [Parameter(Mandatory = $true)]
        [uri] $DownloadUri,

        [bool] $SkipNetworkProfileCheck,

        [int] $CertValidityDays,

        [switch] $ForceNewSSLCert,

        [switch] $GlobalHttpFirewallAccess,

        [switch] $EnableCredSSP,

        [switch] $Force
    )

    $scriptToRun = $null
    $downloadedTemp = $false
    if ($LocalScriptPath -and $LocalScriptPath.Trim().Length -gt 0) {
        if (-not (Test-Path -LiteralPath $LocalScriptPath)) {
            throw "ConfigureRemotingScriptPath not found: $LocalScriptPath"
        }
        $scriptToRun = (Resolve-Path -LiteralPath $LocalScriptPath).Path
        Write-Verbose "Using local ConfigureRemotingForAnsible script: $scriptToRun"
    }
    else {
        $tmp = Join-Path $env:TEMP ("ConfigureRemotingForAnsible.{0}.ps1" -f ([Guid]::NewGuid().ToString('N')))
        Write-Verbose "Downloading ConfigureRemotingForAnsible from: $DownloadUri"
        Invoke-WebRequest -Uri $DownloadUri -OutFile $tmp -UseBasicParsing
        $scriptToRun = $tmp
        $downloadedTemp = $true
    }

    $remotingSplat = @{
        CertValidityDays = $CertValidityDays
    }
    if ($SkipNetworkProfileCheck) {
        $remotingSplat['SkipNetworkProfileCheck'] = $true
    }
    if ($ForceNewSSLCert) {
        $remotingSplat['ForceNewSSLCert'] = $true
    }
    if ($GlobalHttpFirewallAccess) {
        $remotingSplat['GlobalHttpFirewallAccess'] = $true
    }
    if ($EnableCredSSP) {
        $remotingSplat['EnableCredSSP'] = $true
    }

    try {
        if (-not ($Force -or $PSCmdlet.ShouldProcess($scriptToRun, 'Run Ansible ConfigureRemotingForAnsible.ps1'))) {
            Write-Warning 'Skipping WinRM configuration (no -Force and confirmation declined).'
            return
        }
        Write-Host "Running Ansible WinRM bootstrap: $scriptToRun"
        & $scriptToRun @remotingSplat
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            throw "ConfigureRemotingForAnsible.ps1 exited with code $LASTEXITCODE"
        }
    }
    finally {
        if ($downloadedTemp -and (Test-Path -LiteralPath $scriptToRun)) {
            Remove-Item -LiteralPath $scriptToRun -Force -ErrorAction SilentlyContinue
        }
    }
}

if (-not (Test-Administrator)) {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isSystem = ($id.User.Value -eq 'S-1-5-18')
    if (-not ($AllowSystemContext -and $isSystem)) {
        throw 'Run this script from an elevated PowerShell (Run as Administrator), or pass -AllowSystemContext when running as SYSTEM from SetupComplete.cmd.'
    }
    Write-Verbose 'Running as NT AUTHORITY\SYSTEM with -AllowSystemContext (unattended SetupComplete path).'
}

# TLS for Invoke-WebRequest against GitHub / ansible-documentation
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

if (-not $SkipWinRmConfiguration) {
    Invoke-AnsibleConfigureRemotingScript `
        -LocalScriptPath $ConfigureRemotingScriptPath `
        -DownloadUri $AnsibleConfigureRemotingUri `
        -SkipNetworkProfileCheck:([bool]$WinRmSkipNetworkProfileCheck) `
        -CertValidityDays $WinRmCertValidityDays `
        -ForceNewSSLCert:$WinRmForceNewSSLCert `
        -GlobalHttpFirewallAccess:$WinRmGlobalHttpFirewallAccess `
        -EnableCredSSP:$WinRmEnableCredSSP `
        -Force:$Force
}
else {
    Write-Warning 'SkipWinRmConfiguration: not running ConfigureRemotingForAnsible.ps1.'
}

if (-not $SkipFirewallDisable) {
    Disable-WindowsFirewallAllProfiles -Force:$Force

    # Sysprep re-enables the firewall when generalizing.  Register a startup
    # scheduled task so every boot (including clones from this golden image)
    # disables the firewall before any automation EE attempts to reach WinRM.
    $taskName = 'OCPV-DisableFirewall'
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $existingTask) {
        Write-Verbose "Registering startup scheduled task '$taskName' (survives sysprep)."
        $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument '-NoProfile -Command "Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False"'
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest -LogonType ServiceAccount
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings -Force | Out-Null
        Write-Host "Scheduled task '$taskName' registered (runs at every startup as SYSTEM)."
    }
    else {
        Write-Verbose "Scheduled task '$taskName' already exists; skipping creation."
    }
}
else {
    Write-Warning 'SkipFirewallDisable: Windows Firewall left unchanged. AAP/EE may not reach WinRM if profiles block inbound.'
}

# --- Cloudbase-Init install and KubeVirt-oriented config (from legacy Prepare-CloudbaseInitForKubeVirt) ---

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

$nocloudFirst =
    'cloudbaseinit.metadata.services.nocloudservice.NoCloudConfigDriveService,' +
    'cloudbaseinit.metadata.services.configdrive.ConfigDriveService,' +
    'cloudbaseinit.metadata.services.ec2service.EC2Service,' +
    'cloudbaseinit.metadata.services.httpservice.HttpService,' +
    'cloudbaseinit.metadata.services.maasservice.MaaSHttpService'

function Update-CloudbaseMainConf {
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

    if ($text -match 'nocloudservice\.NoCloudConfigDriveService') {
        Write-Verbose "metadata_services already references NoCloud (nocloudservice) in $Path"
    }
    else {
        $removed = [regex]::Replace(
            $text,
            '(?ms)^\s*metadata_services\s*=.*?(?=^[A-Za-z0-9_\[]|\z)',
            '',
            1)
        if ($removed.Length -eq $text.Length) {
            Write-Warning "No metadata_services= block found in $Path; appending new entry only."
        }
        $text = $removed
        $insert = "metadata_services=$nocloudFirst`r`n"
        if ($text -match '\[DEFAULT\]') {
            $text = $text -replace '(\[DEFAULT\]\s*\r?\n)', "`$1$insert"
        }
        else {
            $text = "[DEFAULT]`r`n$insert" + $text
        }
    }

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

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $text, $utf8NoBom)
    Write-Host "Updated $Path"
}

Update-CloudbaseMainConf -Path (Join-Path $cbConfDir 'cloudbase-init.conf')

$unattendCandidates = @(
    (Join-Path $cbConfDir 'Unattend.xml')
    (Join-Path $cbRoot 'Unattend.xml')
)
$unattend = $unattendCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $unattend) {
    throw "Unattend.xml not found under '$cbConfDir'. Reinstall Cloudbase-Init or pass a custom unattend path."
}

Write-Host "Using unattend: $unattend"

Get-Service -Name 'cloudbase-init' -ErrorAction SilentlyContinue | Stop-Service -Force -ErrorAction SilentlyContinue
Get-Service -Name 'cloudbase-init' -ErrorAction SilentlyContinue | Set-Service -StartupType Automatic -ErrorAction SilentlyContinue

if ($SkipSysprep) {
    Write-Warning 'SkipSysprep set: not running sysprep. Shut down manually when ready to capture the disk.'
    exit 0
}

$sysprep = Join-Path $env:SystemRoot 'System32\Sysprep\sysprep.exe'
if (-not (Test-Path -LiteralPath $sysprep)) {
    throw "Sysprep not found at $sysprep"
}

$useOobe = switch ($SysprepOobeMode) {
    'Oobe' { $true }
    'NoOobe' { $false }
    default {
        if (Test-WindowsServerCoreInstallation) { $false }
        else { $true }
    }
}
$oobeLabel = if ($useOobe) { '/generalize /oobe /shutdown' } else { '/generalize /shutdown (no /oobe; Server Core or NoOobe)' }
Write-Host "Launching sysprep $oobeLabel (VM will power off when finished)..."
if (-not $useOobe -and (Test-WindowsServerCoreInstallation)) {
    Write-Verbose 'Server Core detected: skipping /oobe so msoobe/OOBE COM stack is not invoked (avoids REGDB_E_CLASSNOTREG / 0x80040154).'
}
$unattendArg = '/unattend:{0}' -f $unattend
$sysprepArgs = [System.Collections.Generic.List[string]]::new()
$sysprepArgs.Add('/generalize')
if ($useOobe) { $sysprepArgs.Add('/oobe') }
$sysprepArgs.Add('/shutdown')
$sysprepArgs.Add($unattendArg)
$argSummary = ($sysprepArgs -join ' ')
Write-Host "Invoking: $sysprep $argSummary"

if ($Force -or $PSCmdlet.ShouldProcess($sysprep, $argSummary)) {
    & $sysprep @($sysprepArgs.ToArray())
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "sysprep.exe exited with code $LASTEXITCODE"
    }
}
Write-Host 'Sysprep process exited (guest may still be shutting down).'
