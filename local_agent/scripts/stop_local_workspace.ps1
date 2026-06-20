$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\process_manager.ps1")

$result = Stop-LocalAgentStack
Write-Host "P2 本地工作台已停止，共停止 $($result.StoppedCount) 个进程。"

