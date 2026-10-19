$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'wsl-common.ps1')
$runtime = Get-LabWslRuntime -ProjectRoot $root
& wsl.exe -d Ubuntu --cd $runtime.Root --exec $runtime.Python scripts/check_system.py --seconds 30
exit $LASTEXITCODE
