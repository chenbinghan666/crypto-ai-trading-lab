$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'wsl-common.ps1')
$root = Split-Path -Parent $PSScriptRoot
$runtime = Get-LabWslRuntime -ProjectRoot $root
$linuxRoot = $runtime.Root
$runtimePython = $runtime.Python
$wanted = Join-Path $root '.runtime\system-wanted'
$lockPath = Join-Path $root '.runtime\windows-watchdog.lock'
try { $lockStream = [System.IO.File]::Open($lockPath,'OpenOrCreate','ReadWrite','None') }
catch { exit 0 }
try {
    while (Test-Path -LiteralPath $wanted) {
        & wsl.exe -d Ubuntu --cd $linuxRoot --exec $runtimePython -m labapp.supervisor 2>&1 | Out-File -FilePath (Join-Path $root 'logs\windows-watchdog.log') -Append -Encoding utf8
        if (Test-Path -LiteralPath $wanted) { Start-Sleep -Seconds 5 }
    }
} finally { $lockStream.Dispose() }
