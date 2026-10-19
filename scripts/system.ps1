param([ValidateSet('start','stop','status','credentials')][string]$Command = 'start', [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'wsl-common.ps1')
$root = Split-Path -Parent $PSScriptRoot
$runtime = Get-LabWslRuntime -ProjectRoot $root
$linuxRoot = $runtime.Root
$runtimePython = $runtime.Python
if ($Command -ne 'start') {
    if ($Command -eq 'stop') {
        Remove-Item -LiteralPath (Join-Path $root '.runtime\system-wanted') -ErrorAction SilentlyContinue
    }
    & wsl.exe -d Ubuntu --cd $linuxRoot --exec $runtimePython -m labapp.control $Command
    exit $LASTEXITCODE
}
& wsl.exe -d Ubuntu --cd $linuxRoot --exec $runtimePython -m labapp.control is-running
if ($LASTEXITCODE -ne 0) {
    # A detached, hidden WSL host keeps services alive after the launcher/Codex closes.
    New-Item -ItemType Directory -Force -Path (Join-Path $root '.runtime') | Out-Null
    Set-Content -LiteralPath (Join-Path $root '.runtime\system-wanted') -Value 'infrastructure-only'
    $watchdogPath = '"' + (Join-Path $PSScriptRoot 'watchdog.ps1') + '"'
    Start-Process -FilePath powershell.exe -WindowStyle Hidden -WorkingDirectory $root -RedirectStandardOutput (Join-Path $root 'logs\watchdog-host.log') -RedirectStandardError (Join-Path $root 'logs\watchdog-host-error.log') -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$watchdogPath) | Out-Null
}
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 2
        if ($health.status -eq 'ok') { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw '启动超时。请查看 logs/*-service.log，或运行 查看状态.cmd。' }
Write-Host '系统已启动：http://127.0.0.1:8080 ；网页可操作 AI、回测与模拟。模拟实际状态见网页；实盘始终禁止。'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8080' }
