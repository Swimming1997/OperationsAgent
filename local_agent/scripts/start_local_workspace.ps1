param(
    [string]$Config = "",
    [string]$AccountKey = "local-workspace",
    [int]$ChromePort = 9222
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

$LocalAgentRoot = $script:LocalAgentRoot
$RepoRoot = $script:RepoRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$RunScript = Join-Path $PSScriptRoot "run_local_agent.py"
$ChromeScript = Join-Path $PSScriptRoot "start_account_chrome.py"
$LogsDir = Join-Path $LocalAgentRoot "logs"
$RuntimeDir = Join-Path $LogsDir "runtime"
$StdoutPath = Join-Path $RuntimeDir "workspace.out.log"
$StderrPath = Join-Path $RuntimeDir "workspace.err.log"

if (!$Config) {
    $Config = if ($env:LOCAL_AGENT_CONFIG) {
        $env:LOCAL_AGENT_CONFIG
    } else {
        Join-Path $LocalAgentRoot "configs\local_agent.employee.example.toml"
    }
}
if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "未找到项目 Python 环境：$PythonExe"
}
if (!(Test-Path -LiteralPath $Config)) {
    throw "未找到 Local Agent 配置：$Config"
}

New-Item -ItemType Directory -Force -Path $LogsDir, $RuntimeDir | Out-Null
Stop-LocalAgentStack | Out-Null

if (!(Get-BridgePortListenerPid -BindHost "127.0.0.1" -Port $ChromePort)) {
    & $PythonExe $ChromeScript --account-key $AccountKey --port $ChromePort
    if ($LASTEXITCODE -ne 0) {
        throw "Chrome 启动失败，请确认已安装 Chrome 或 Edge。"
    }
    Start-Sleep -Milliseconds 800
}

$arguments = @(
    "-u",
    $RunScript,
    "--config", $Config,
    "--log-dir", $LogsDir,
    "--project-root", $LocalAgentRoot,
    "--cdp-url", "http://127.0.0.1:$ChromePort"
)

$process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $arguments `
    -WorkingDirectory $LocalAgentRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdoutPath `
    -RedirectStandardError $StderrPath `
    -PassThru

$workspaceUrl = $null
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ($process.HasExited) {
        break
    }
    if (Test-Path -LiteralPath $StdoutPath) {
        $output = Get-Content -LiteralPath $StdoutPath -Raw -ErrorAction SilentlyContinue
        if ($output -match "local_workspace=(http://[^\s]+)") {
            $workspaceUrl = $Matches[1]
            break
        }
    }
    Start-Sleep -Milliseconds 250
}

if (!$workspaceUrl) {
    $errorText = if (Test-Path -LiteralPath $StderrPath) {
        Get-Content -LiteralPath $StderrPath -Raw
    } else {
        "没有错误日志。"
    }
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "真实本地工作台启动失败。`n$errorText"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " P2 真实本地工作台已启动" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "1. 先在自动打开的 Chrome/Edge 中登录小红书。"
Write-Host "2. 再到工作台输入关键词并点击“开始采集”。"
Write-Host "3. 页面只显示真实采集到的内容，不再生成模拟数据。"
Write-Host ""
Write-Host "工作台：$workspaceUrl"
Write-Host "停止：双击项目根目录的“停止本地工作台.bat”"
Write-Host ""

Start-Process $workspaceUrl
