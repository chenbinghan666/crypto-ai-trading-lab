# WSL writes UTF-8. Windows PowerShell 5.1 otherwise decodes native output
# using the console's legacy code page, corrupting Chinese project paths.
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-LabWslRuntime {
    param([Parameter(Mandatory=$true)][string]$ProjectRoot)
    $converted = @(& wsl.exe -d Ubuntu --exec wslpath -a $ProjectRoot.Replace('\','/'))
    if ($LASTEXITCODE -ne 0 -or $converted.Count -ne 1) {
        throw '无法解析 WSL 项目路径，请确认 Ubuntu 可用。'
    }
    $projectLinuxPath = ([string]$converted[0]).Trim()
    $homeOutput = @(& wsl.exe -d Ubuntu --exec printenv HOME)
    if ($LASTEXITCODE -ne 0 -or $homeOutput.Count -ne 1) {
        throw '无法读取 WSL 用户目录。'
    }
    $runtimeHome = ([string]$homeOutput[0]).Trim()
    if (-not $projectLinuxPath.StartsWith('/') -or -not $runtimeHome.StartsWith('/')) {
        throw 'WSL 路径格式异常，已停止执行。'
    }
    $pythonPath = "$runtimeHome/.local/share/crypto-ai-trading-lab/venv/bin/python"
    & wsl.exe -d Ubuntu --cd $projectLinuxPath --exec $pythonPath -c 'import pathlib,sys; assert pathlib.Path.cwd().resolve() == pathlib.Path(sys.argv[1]).resolve(); import labapp.control' $projectLinuxPath
    if ($LASTEXITCODE -ne 0) {
        throw 'WSL 无法加载本项目，请检查项目目录及 Python 环境；未执行管理操作。'
    }
    return [PSCustomObject]@{Root=$projectLinuxPath;Home=$runtimeHome;Python=$pythonPath}
}
