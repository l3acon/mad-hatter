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
  Log ("SetupPhase={0} SetupType={1} SystemSetupInProgress={2}" -f $sp, $st, $ssip)
  $oobePath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE'
  $oobeProg = $null
  if (Test-Path $oobePath) {
    $oobeProg = (Get-ItemProperty -Path $oobePath -Name OOBEInProgress -ErrorAction SilentlyContinue).OOBEInProgress
    Log ("OOBEInProgress={0}" -f $oobeProg)
  }
  $stuck = ($ssip -eq 1) -or ($oobeProg -eq 1) -or ($sp -eq 4)
  if (-not $stuck) {
    Log 'not stuck (skip)'
    exit 0
  }
  Log 'clearing stuck mini-setup / clone setup flags'
  Set-ItemProperty -Path $setup -Name 'SetupPhase' -Value 0 -Type DWord -Force
  Set-ItemProperty -Path $setup -Name 'SetupType' -Value 0 -Type DWord -Force
  Set-ItemProperty -Path $setup -Name 'SystemSetupInProgress' -Value 0 -Type DWord -Force
  if (Test-Path $oobePath) {
    New-ItemProperty -Path $oobePath -Name 'OOBEInProgress' -Value 0 -PropertyType DWord -Force -ErrorAction SilentlyContinue | Out-Null
    Set-ItemProperty -Path $oobePath -Name 'OOBEInProgress' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
  }
  $state = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Setup\State'
  if (Test-Path $state) {
    Set-ItemProperty -Path $state -Name 'ImageState' -Value 'IMAGE_STATE_COMPLETE' -Force -ErrorAction SilentlyContinue
  }
  Log 'scheduling reboot'
  & (Join-Path $env:SystemRoot 'System32\shutdown.exe') /r /t 45 /c 'OpenShift virt: cleared stuck Windows setup state after clone; rebooting.'
}
catch {
  Log ("error: {0}" -f $_.Exception.Message)
  exit 1
}
