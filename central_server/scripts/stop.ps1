$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

Write-Host ""
Write-Host "========================================================================"
Write-Host " Stop AMiracle Central Server"
Write-Host "========================================================================"

$result = Stop-CentralStack
Write-Host "FastAPI 8000 free: $($result.FastApiFree)"
Write-Host "Vite 5173 free:    $($result.ViteFree)"
Write-Host "Local Agent was not stopped."

if ($result.FastApiFree -and $result.ViteFree) { exit 0 }
exit 1
