param([switch]$NoFrontend)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

$RepoRoot = $script:RepoRoot
$CentralRoot = $script:CentralRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LogsDir = Join-Path $CentralRoot "logs"
$RuntimeDir = Join-Path $LogsDir "runtime"
$FrontendDir = Join-Path $CentralRoot "frontend"
$FastApiPort = $script:CentralFastApiPort
$VitePort = $script:CentralVitePort
$HealthUrl = "http://127.0.0.1:$FastApiPort/api/health"
$FrontendUrl = "http://127.0.0.1:$VitePort"

function Ensure-Directory([string]$Path) {
    if (!(Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Wait-HttpReady([string]$Url, [int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        }
        catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

Ensure-Directory $LogsDir
Ensure-Directory $RuntimeDir
Ensure-Directory (Join-Path $CentralRoot "data")

if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "项目虚拟环境 Python 不存在: $PythonExe"
}

Write-Host ""
Write-Host "========================================================================"
Write-Host " AMiracle Central Server"
Write-Host "========================================================================"
Write-Host "  FastAPI: http://127.0.0.1:$FastApiPort"
Write-Host "  Vite:    $FrontendUrl"
Write-Host "  注意：此脚本不启动或停止 Local Agent，也不管理 Chrome。"
Write-Host "========================================================================"

Write-CentralStep "Stopping previous central processes"
$stopResult = Stop-CentralStack
if (-not $stopResult.FastApiFree) {
    throw "FastAPI port $FastApiPort is still in use by a process without a central PID file. Stop it manually or check central_server\logs\runtime."
}
if (-not $NoFrontend -and -not $stopResult.ViteFree) {
    throw "Vite port $VitePort is still in use by a process without a central PID file. Stop it manually or check central_server\logs\runtime."
}

$FastApiLog = Join-Path $LogsDir "fastapi.log"
$FastApiErrLog = Join-Path $LogsDir "fastapi.err.log"
Remove-Item -LiteralPath $FastApiLog, $FastApiErrLog -Force -ErrorAction SilentlyContinue

Write-CentralStep "Starting FastAPI"
$fastApiProc = Start-Process -FilePath $PythonExe -ArgumentList @(
    "-m", "uvicorn", "intelligence_engine.main:app", "--host", "127.0.0.1", "--port", "$FastApiPort"
) -WorkingDirectory $CentralRoot -RedirectStandardOutput $FastApiLog -RedirectStandardError $FastApiErrLog -WindowStyle Hidden -PassThru
Save-CentralRuntimePid -Name "fastapi" -ProcessId $fastApiProc.Id

if (Wait-HttpReady -Url $HealthUrl -TimeoutSeconds 60) {
    $fastApiPortPids = @(Get-PidsByPort -Port $FastApiPort)
    if ($fastApiPortPids.Count -gt 0) {
        Save-CentralRuntimePid -Name "fastapi" -ProcessId $fastApiPortPids[0]
    }
    Write-CentralStep "Backend ready: $HealthUrl"
}
else {
    Write-CentralStep "Backend not ready in 60s. See $FastApiLog and $FastApiErrLog"
}

if (-not $NoFrontend) {
    if (!(Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
        Write-CentralStep "frontend/node_modules 不存在，请在 central_server\frontend 执行 npm install"
    }
    else {
        $ViteLog = Join-Path $LogsDir "vite.out.log"
        $ViteErrLog = Join-Path $LogsDir "vite.err.log"
        Remove-Item -LiteralPath $ViteLog, $ViteErrLog -Force -ErrorAction SilentlyContinue
        $npmCmd = (Get-Command "npm.cmd" -ErrorAction SilentlyContinue).Source
        if (-not $npmCmd) { $npmCmd = "npm" }
        Write-CentralStep "Starting Vite"
        $viteProc = Start-Process -FilePath $npmCmd -ArgumentList @("run", "dev") -WorkingDirectory $FrontendDir -RedirectStandardOutput $ViteLog -RedirectStandardError $ViteErrLog -WindowStyle Hidden -PassThru
        Save-CentralRuntimePid -Name "vite" -ProcessId $viteProc.Id
        if (Wait-HttpReady -Url $FrontendUrl -TimeoutSeconds 45) {
            $vitePortPids = @(Get-PidsByPort -Port $VitePort)
            if ($vitePortPids.Count -gt 0) {
                Save-CentralRuntimePid -Name "vite" -ProcessId $vitePortPids[0]
            }
            Write-CentralStep "Frontend ready: $FrontendUrl"
        }
        else {
            Write-CentralStep "Frontend may still be compiling: $FrontendUrl"
        }
    }
}

Write-Host ""
Write-Host "Central startup complete."
Write-Host "Logs: $LogsDir"
