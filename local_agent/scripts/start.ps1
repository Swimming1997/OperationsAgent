param(
    [string]$Config = "",
    [switch]$Once
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

$LocalAgentRoot = $script:LocalAgentRoot
$RepoRoot = $script:RepoRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$RunScript = Join-Path $LocalAgentRoot "scripts\run_local_agent.py"
$LogsDir = Join-Path $LocalAgentRoot "logs"

if ($Config) {
    $ConfigPath = $Config
}
elseif ($env:LOCAL_AGENT_CONFIG) {
    $ConfigPath = $env:LOCAL_AGENT_CONFIG
}
else {
    $ConfigPath = Join-Path $LocalAgentRoot "configs\local_agent.employee.example.toml"
}

if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "项目虚拟环境 Python 不存在: $PythonExe"
}
if (!(Test-Path -LiteralPath $ConfigPath)) {
    throw "Local Agent 配置不存在: $ConfigPath"
}

New-Item -ItemType Directory -Force -Path $LogsDir, (Join-Path $LogsDir "runtime"), (Join-Path $LocalAgentRoot "profiles\accounts") | Out-Null

$HealthUrl = "http://127.0.0.1:8000/api/health"
try {
    $health = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
    if ($health.StatusCode -ne 200) { throw "HTTP $($health.StatusCode)" }
}
catch {
    Write-Host "[Local Agent] 中央 API 不可达: $HealthUrl" -ForegroundColor Red
    Write-Host "请先启动中央服务，并等待 /api/health 返回 ok。"
    Write-Host "错误详情: $($_.Exception.Message)"
    exit 1
}

Set-Location -LiteralPath $LocalAgentRoot
$argsList = @($RunScript, "--config", $ConfigPath, "--log-dir", $LogsDir, "--project-root", $LocalAgentRoot)
if ($Once) { $argsList += "--once" }

& $PythonExe @argsList
exit $LASTEXITCODE
