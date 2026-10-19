$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'wsl-common.ps1')
$ProgressPreference = 'SilentlyContinue'
$systemPath = (Join-Path $PSScriptRoot 'system.ps1').Replace("'","''")
$credentialsPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'FreqUI登录信息.cmd').Replace("'","''")
$results = @()
foreach ($codePage in @(936,437,65001)) {
    $template = @'
[Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(__CODEPAGE__)
$ProgressPreference = 'SilentlyContinue'
$OutputEncoding = [System.Text.Encoding]::ASCII
$statusText = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File '__SYSTEM__' status 2>&1) -join "`n"
$statusExit = $LASTEXITCODE
$commandLine = 'call "__CREDENTIALS__" <nul'
$credentialText = (& cmd.exe /d /c $commandLine 2>&1) -join "`n"
$credentialExit = $LASTEXITCODE
# Never echo raw credential output or include it in the evidence file.
$result = [PSCustomObject]@{
    InitialCodePage=__CODEPAGE__
    StatusLoaded=($statusExit -eq 0 -and $statusText -match '"running": true')
    CredentialLauncherWorks=($credentialExit -eq 0 -and $credentialText -match 'http://127.0.0.1:8081' -and $credentialText -match 'localadmin')
    NoPathErrors=($statusText -notmatch 'chdir\(|ModuleNotFoundError' -and $credentialText -notmatch 'chdir\(|ModuleNotFoundError')
}
$credentialText = $null
$statusText = $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$result | ConvertTo-Json -Compress
'@
    $payload = $template.Replace('__CODEPAGE__',[string]$codePage).Replace('__SYSTEM__',$systemPath).Replace('__CREDENTIALS__',$credentialsPath)
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($payload))
    $output = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Launcher test failed for code page $codePage" }
    $results += ($output | ConvertFrom-Json)
}
$passed = @($results | Where-Object { -not ($_.StatusLoaded -and $_.CredentialLauncherWorks -and $_.NoPathErrors) }).Count -eq 0
$report = [PSCustomObject]@{CheckedAt=(Get-Date -Format o);Passed=$passed;Results=$results;CredentialsIncluded=$false}
$target = Join-Path (Split-Path -Parent $PSScriptRoot) 'reports\evidence\phase3\windows-launchers.json'
$json = $report | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($target,$json,[System.Text.UTF8Encoding]::new($false))
$json
if (-not $passed) { exit 1 }
