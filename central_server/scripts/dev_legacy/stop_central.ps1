# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
param([switch]$NoPause)

$ErrorActionPreference = "SilentlyContinue"

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

Write-Host ""
Write-Host "========================================================================"
Write-Host " Stop AMiracle Central (FastAPI + Vite)"
Write-Host "========================================================================"
Write-Host ""

$result = Stop-AmiracleCentralStack

Write-Host ""
if ($result.PortStatus.FastApi) {
    Write-Host "  [OK] Port 8000 (FastAPI) free"
} else {
    Write-Host "  [!!] Port 8000 still in use"
}
if ($result.PortStatus.Vite) {
    Write-Host "  [OK] Port 5173 (Vite) free"
} else {
    Write-Host "  [!!] Port 5173 still in use"
}
Write-Host ""
Write-Host "  Local Agent was NOT stopped. Use cd local_agent; .\scripts\stop.ps1 if needed."
Write-Host ""

if ($result.PortsReleased) { exit 0 }
exit 1
