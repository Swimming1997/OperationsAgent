$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

Write-Host ""
Write-Host "========================================================================"
Write-Host " Stop AMiracle Local Agent"
Write-Host "========================================================================"

$result = Stop-LocalAgentStack
Write-Host "Stopped Local Agent process(es): $($result.StoppedCount)"
Write-Host "Central server was not stopped."
exit 0
