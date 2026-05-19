$ErrorActionPreference = 'Stop'
$log = 'C:\Windows\Temp\ocpv-unstick-clone-setup.log'
function Log([string]$m) {
  Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format o), $m) -ErrorAction SilentlyContinue
}
try {
  Log 'start'
  $setup = 'HKLM:\SYSTEM\Setup'
  if (-not (Test-Path $setup)) {
    Log 'no HKLM\SYSTEM\Setup'
    exit 0
  }
  $sp = (Get-ItemProperty -Path $setup -Name SetupPhase -ErrorAction SilentlyContinue).SetupPhase
  $st = (Get-ItemProperty -Path $setup -Name SetupType -ErrorAction SilentlyContinue).SetupType
  $ssip = (Get-ItemProperty -Path $setup -Name SystemSetupInProgress -ErrorAction SilentlyContinue).SystemSetupInProgress
  $cmdLine = (Get-ItemProperty -Path $setup -Name CmdLine -ErrorAction SilentlyContinue).CmdLine
  Log ("SetupPhase={0} SetupType={1} SystemSetupInProgress={2}" -f $sp, $st, $ssip)
  $oobePath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE'
  $oobeProg = $null
  if (Test-Path $oobePath) {
    $oobeProg = (Get-ItemProperty -Path $oobePath -Name OOBEInProgress -ErrorAction SilentlyContinue).OOBEInProgress
    Log ("OOBEInProgress={0}" -f $oobeProg)
  }
  # Common loop for "computer restarted unexpectedly / installation cannot proceed":
  # HKLM\SYSTEM\Setup\Status\ChildCompletion "setup.exe" = 1 -> set 3 (forces next setup stage).
  # Ref: https://woshub.com/windows-install-error-computer-restarted-unexpectedly/
  $child = 'HKLM:\SYSTEM\Setup\Status\ChildCompletion'
  $childSetup = $null
  if (Test-Path $child) {
    $childSetup = (Get-ItemProperty -Path $child -Name 'setup.exe' -ErrorAction SilentlyContinue).'setup.exe'
    Log ("ChildCompletion\setup.exe={0}" -f $childSetup)
  }
  $fixChild = ($childSetup -eq 1)
  $fixSetupKeys = ($ssip -eq 1) -or ($oobeProg -eq 1) -or ($sp -in 4, 7)
  if (-not ($fixChild -or $fixSetupKeys)) {
    Log 'no known stuck mini-setup pattern (skip)'
    exit 0
  }
  Log 'applying clone / mini-setup recovery registry fixes'
  if ($fixChild) {
    Set-ItemProperty -Path $child -Name 'setup.exe' -Value 3 -Type DWord -Force
    Log 'ChildCompletion setup.exe -> 3'
  }
  if ($fixSetupKeys) {
    Set-ItemProperty -Path $setup -Name 'SetupPhase' -Value 0 -Type DWord -Force
    Set-ItemProperty -Path $setup -Name 'SetupType' -Value 0 -Type DWord -Force
    Set-ItemProperty -Path $setup -Name 'SystemSetupInProgress' -Value 0 -Type DWord -Force
    if (Test-Path $oobePath) {
      New-ItemProperty -Path $oobePath -Name 'OOBEInProgress' -Value 0 -PropertyType DWord -Force -ErrorAction SilentlyContinue | Out-Null
      Set-ItemProperty -Path $oobePath -Name 'OOBEInProgress' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
    }
    if ($cmdLine) {
      Remove-ItemProperty -Path $setup -Name 'CmdLine' -Force -ErrorAction SilentlyContinue
      Log 'removed Setup CmdLine'
    }
  }
  Log 'scheduling reboot'
  & (Join-Path $env:SystemRoot 'System32\shutdown.exe') /r /t 45 /c 'OpenShift virt: cleared stuck Windows setup state after clone; rebooting.'
}
catch {
  Log ("error: {0}" -f $_.Exception.Message)
  exit 1
}
