# WinPE / early setup: load VirtIO block driver from the virtio-win CD-ROM so the virtio system disk is visible.
# Invoked from Autounattend.xml RunSynchronous (answer ISO) or manually.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$chosen = $null
foreach ($v in Get-Volume | Where-Object { $_.DriveType -eq 'CD-ROM' }) {
    if (-not $v.DriveLetter) { continue }
    $root = $v.DriveLetter + ':'
    foreach ($rel in @(
            'amd64\2k22\viostor.inf',
            'amd64\w11\viostor.inf',
            'amd64\w10\viostor.inf',
            'amd64\2k19\viostor.inf',
            'amd64\2k16\viostor.inf',
            'viostor\w11\amd64\viostor.inf',
            'viostor\w10\amd64\viostor.inf',
            'viostor\2k22\amd64\viostor.inf',
            'vioscsi\w11\amd64\vioscsi.inf',
            'vioscsi\w10\amd64\vioscsi.inf'
        )) {
        $p = Join-Path $root $rel
        if (Test-Path -LiteralPath $p) {
            $chosen = $p
            break
        }
    }
    if ($chosen) { break }
}

if (-not $chosen) {
    Write-Error 'VirtIO storage driver INF not found on any CD-ROM volume (expect kubevirt virtio container disk).'
    exit 1
}

$pnp = Join-Path $env:WINDIR 'System32\pnputil.exe'
if (-not (Test-Path -LiteralPath $pnp)) {
    $pnp = 'pnputil.exe'
}
& $pnp /add-driver $chosen /install
exit $LASTEXITCODE
