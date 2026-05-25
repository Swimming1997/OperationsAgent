# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
# Start central stack only: FastAPI + Vite. Does NOT start Local Agent or demo Chrome.

param(
    [switch]$NoFrontend
)

$ErrorActionPreference = "Stop"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

$ProjectRoot = $script:AmiracleProjectRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogsDir = Join-Path $ProjectRoot "logs"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$FastApiLog = Join-Path $LogsDir "fastapi.log"
$FastApiErrLog = Join-Path $LogsDir "fastapi.err.log"
$ViteLog = Join-Path $LogsDir "vite.out.log"
$ViteErrLog = Join-Path $LogsDir "vite.err.log"
$FastApiPort = $script:AmiracleFastApiPort
$VitePort = $script:AmiracleVitePort
$FastApiUrl = "http://127.0.0.1:$FastApiPort/api/health"
$FrontendUrl = "http://127.0.0.1:$VitePort"

function Ensure-Directory {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

function Update-PidFromPort {
    param(
        [string]$Name,
        [int]$Port
    )
    Start-Sleep -Milliseconds 800
    $pids = @(Get-PidsByPort -Port $Port)
    if ($pids.Count -gt 0) {
        Save-AmiracleRuntimePid -Name $Name -ProcessId $pids[0]
    }
}

Set-Location -LiteralPath $ProjectRoot
Ensure-Directory $LogsDir
Ensure-Directory (Join-Path $ProjectRoot "data")
Ensure-AmiracleRuntimeDir

if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "Project venv Python not found: $PythonExe"
}

Write-Host ""
Write-Host "========================================================================"
Write-Host " AMiracle Central (API + Web UI)"
Write-Host "========================================================================"
Write-Host "  This script does NOT start Local Agent."
Write-Host "  For account login / Chrome profiles on this PC, run:"
Write-Host "    cd local_agent; .\scripts\start.ps1"
Write-Host "========================================================================"
Write-Host ""

Write-AmiracleStep "Stopping previous central processes"
Stop-AmiracleCentralStack | Out-Null
Start-Sleep -Seconds 1

Write-AmiracleStep "Starting FastAPI: http://127.0.0.1:$FastApiPort"
foreach ($logPath in @($FastApiLog, $FastApiErrLog)) {
    if (Test-Path -LiteralPath $logPath) {
        Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
    }
}

$fastApiProc = Start-Process -FilePath $PythonExe -ArgumentList @(
    "-m",
    "uvicorn",
    "intelligence_engine.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$FastApiPort"
) -WorkingDirectory $ProjectRoot -RedirectStandardOutput $FastApiLog -RedirectStandardError $FastApiErrLog -WindowStyle Hidden -PassThru

Save-AmiracleRuntimePid -Name "fastapi" -ProcessId $fastApiProc.Id
Update-PidFromPort -Name "fastapi" -Port $FastApiPort

if (Wait-HttpReady -Url $FastApiUrl -TimeoutSeconds 60) {
    Write-AmiracleStep "Backend ready (DB init runs on startup): $FastApiUrl"
}
else {
    Write-AmiracleStep "Backend not ready in 60s. See: $FastApiLog / $FastApiErrLog"
}

if (-not $NoFrontend) {
    if (!(Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
        Write-AmiracleStep "WARN: frontend/node_modules missing. Run: cd frontend && npm install"
    }
    else {
        Write-AmiracleStep "Starting Vite: $FrontendUrl"
        foreach ($logPath in @($ViteLog, $ViteErrLog)) {
            if (Test-Path -LiteralPath $logPath) {
                Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
            }
        }
        $npmCmd = (Get-Command "npm.cmd" -ErrorAction SilentlyContinue).Source
        if (-not $npmCmd) { $npmCmd = "npm" }
        $viteProc = Start-Process -FilePath $npmCmd -ArgumentList @("run", "dev") -WorkingDirectory $FrontendDir `
            -RedirectStandardOutput $ViteLog -RedirectStandardError $ViteErrLog -WindowStyle Hidden -PassThru
        Save-AmiracleRuntimePid -Name "vite" -ProcessId $viteProc.Id
        Update-PidFromPort -Name "vite" -Port $VitePort
        if (Wait-HttpReady -Url $FrontendUrl -TimeoutSeconds 45) {
            Write-AmiracleStep "Frontend ready: $FrontendUrl"
        }
        else {
            Write-AmiracleStep "Frontend may still compile. Try: $FrontendUrl"
        }
    }
}

Write-Host ""
Write-Host "========================================================================"
Write-Host " Central startup complete"
Write-Host "========================================================================"
Write-Host "  Frontend:  $FrontendUrl"
Write-Host "  Backend:   http://127.0.0.1:$FastApiPort"
Write-Host "  Health:    $FastApiUrl"
Write-Host "  Logs:      logs\fastapi.log  logs\vite.out.log"
Write-Host ""
Write-Host "  Local Agent: NOT started (by design)"
Write-Host "  Next:        cd local_agent; .\scripts\start.ps1  (separate window)"
Write-Host ""
Write-Host "  Stop central: cd central_server; .\scripts\stop.ps1"
Write-Host "========================================================================"
