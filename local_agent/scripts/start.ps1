param(
    [string]$Config = "",
    [switch]$Once
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

function Resolve-BrowserExecutable {
    $candidates = @(
        $env:CHROME_PATH,
        $env:BROWSER_PATH,
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    ) | Where-Object { $_ -and $_.Trim().Length -gt 0 } | Select-Object -Unique

    foreach ($item in $candidates) {
        if (Test-Path -LiteralPath $item) {
            return (Resolve-Path -LiteralPath $item).Path
        }
    }
    return $null
}

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
    throw "Python venv not found: $PythonExe"
}
if (!(Test-Path -LiteralPath $ConfigPath)) {
    throw "Local Agent config not found: $ConfigPath"
}

New-Item -ItemType Directory -Force -Path $LogsDir, (Join-Path $LogsDir "runtime"), (Join-Path $LocalAgentRoot "profiles\accounts") | Out-Null

$HealthUrl = "http://127.0.0.1:8000/api/health"
try {
    $health = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
    if ($health.StatusCode -ne 200) { throw "HTTP $($health.StatusCode)" }
}
catch {
    Write-Host "[Local Agent] Central API unreachable: $HealthUrl" -ForegroundColor Red
    Write-Host "Start central_server first and wait until /api/health is ok."
    Write-Host "Error: $($_.Exception.Message)"
    exit 1
}

Set-Location -LiteralPath $LocalAgentRoot
$argsList = @($RunScript, "--config", $ConfigPath, "--log-dir", $LogsDir, "--project-root", $LocalAgentRoot)
if ($Once) { $argsList += "--once" }

$browserExe = Resolve-BrowserExecutable
if ($browserExe) {
    if (-not $env:CHROME_PATH) { $env:CHROME_PATH = $browserExe }
    if (-not $env:BROWSER_PATH) { $env:BROWSER_PATH = $browserExe }
    Write-Host "[Local Agent] browser executable: $browserExe"
} else {
    Write-Host "[Local Agent] Chrome/Edge not found. Set CHROME_PATH or BROWSER_PATH first." -ForegroundColor Yellow
}

& $PythonExe @argsList
exit $LASTEXITCODE
