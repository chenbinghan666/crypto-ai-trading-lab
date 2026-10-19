param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('check','download-data','run-backtest','start-paper','stop-paper','status','generate-report','test')]
    [string]$Command
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'wsl-common.ps1')
$root = Split-Path -Parent $PSScriptRoot
$runtime = Get-LabWslRuntime -ProjectRoot $root
& wsl.exe -d Ubuntu --cd $runtime.Root --exec $runtime.Python scripts/lab.py $Command
exit $LASTEXITCODE
